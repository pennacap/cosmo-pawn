import imghdr
import discord
from discord.ext import commands, tasks
import requests
import os
import dotenv
import threading
import flask
import sqlite3
import re
import hashlib
import asyncio

flask_app = flask.Flask(__name__)


@flask_app.route('/')
def index():
    return flask.render_template("index.html")


@flask_app.route('/docs')
def docs():
    return flask.render_template("docs.html")


@flask_app.route('/upload', methods=["POST"])
def upload():

    if 'Keywords' not in flask.request.headers or not len(map(str.strip, flask.request.headers.get('Keywords').split(','))):
        return flask.abort(flask.Response(status=400, response="Keywords header missing or no keyword used"))
    hash = hashlib.sha256(flask.request.get_data()).hexdigest()

    if bot.db.execute('SELECT * FROM items WHERE hash = ?', [hash]).fetchone():
        return flask.abort(flask.Response(status=400, response=f"This image has already been uploaded!"))
    if not imghdr.what('', h=flask.request.get_data()):
        raise flask.abort(flask.Response(
            status=400, response=f"Invalid image!"))
    for i in map(str.strip, flask.request.headers.get('Keywords').split(',')):
        if re.search('[^a-zA-Z ]', str(i)):
            return flask.abort(flask.Response(status=400, response=f"Invalid keywords '{i}'!"))
    id = bot.db.execute('SELECT COUNT(path) FROM items').fetchone()[0]+1
    for i in map(str.strip, flask.request.headers.get('Keywords').split(',')):
        if str(i).lower() not in keywords:
            keywords[str(i).lower()] = 0
            bot.db.execute('INSERT INTO keywords VALUES (?)', [str(i).lower()])
        keywords[str(i).lower()] += 1
    with open("images/"+str(id)+"."+imghdr.what('', h=flask.request.get_data()), 'wb') as f:
        f.write(flask.request.get_data())

    bot.db.execute('INSERT INTO items VALUES (?, ?, 0, ?, ?)', [str(id) + '.' + imghdr.what('', h=flask.request.get_data(
    )), ''.join([i.lower()+'|' for i in map(str.strip, flask.request.headers.get('Keywords').split(','))]), 0, hash])
    return flask.jsonify({'id': id})


@flask_app.route('/openapi.json')
def openapi():
    return flask.send_file("openapi.json")


@flask_app.route('/items/<imageid>')
async def items(imageid):
    data = bot.db.execute(
        'SELECT * FROM items WHERE path = ? AND verified = 1', [imageid]).fetchone()
    user = bot.get_user(data[3])
    if user:
        return flask.render_template("item.html", keywords=data[1].split('|')[:-1], path=data[0], username=user.name, avatar=user.display_avatar.url)
    else:
        return flask.render_template("item.html", keywords=data[1].split('|')[:-1], path=data[0])


@flask_app.route('/images/<imageid>')
def _image(imageid):
    if '..' in imageid or '/' in imageid:
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    if not os.path.exists(f'images/{imageid}'):
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    return flask.send_file(f'images/{imageid}', max_age=604800)


@flask_app.route('/keywords/<keyword>.sha256')
def keywords_hash(keyword):
    if re.search('[^a-zA-Z ]', keyword):
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    items = bot.db.execute('SELECT * FROM items WHERE keywords LIKE "%' +
                           keyword.lower()+'|%" AND verified = 1').fetchall()

    if not len(items):
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    return flask.jsonify({p[0]: p[4] for p in items})


dotenv.load_dotenv()

bot = commands.Bot(intents=discord.Intents.all(), command_prefix='!')
bot.db = sqlite3.connect("dev.db", check_same_thread=False)
bot.db.execute("CREATE TABLE IF NOT EXISTS items (path TEXT PRIMARY KEY NOT NULL, keywords TEXT NOT NULL, verified BOOLEAN NOT NULL, by INTEGER, hash TEXT UNIQUE NOT NULL)")
bot.db.execute("CREATE TABLE IF NOT EXISTS keywords (name STRING NOT NULL)")
bot.db.execute(
    "CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY NOT NULL, submitted INTEGER, accepted INTEGER)")

keywords = {i[0]: bot.db.execute("SELECT count(path) FROM items WHERE keywords LIKE '%" +
                                 i[0]+"|%'").fetchone()[0] for i in bot.db.execute("SELECT * FROM KEYWORDS").fetchall()}


@flask_app.route('/<keyword>')
def keyword(keyword):
    if re.search('[^a-zA-Z ]', keyword):
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    items = bot.db.execute('SELECT * FROM items WHERE keywords LIKE "%' +
                           keyword.lower()+'|%" AND verified = 1').fetchall()

    if not len(items):
        return flask.abort(flask.Response(status=404, response="{\"message\":\"Not found\"}", content_type="application/json"))
    return flask.jsonify([p[0] for p in items])


@flask_app.route('/keywords')
def kws():
    return flask.jsonify(keywords)


@bot.command(description='Add the file (!add link ...keywords) or (!add ...keywords) if you have an attachment?')
async def add(ctx, *kws):
    try:
        if ctx.message.attachments:
            req_data = await ctx.message.attachments[0].read()
        else:
            req_data = requests.get(kws[0])
            if not req_data.ok:
                raise Exception
            req_data = req_data.content
            kws = list(kws)[1:]
        if not len(kws):
            return await ctx.send(f"There must be atleast one keyword used!")
        hash = hashlib.sha256(req_data).hexdigest()

        if bot.db.execute('SELECT * FROM items WHERE hash = ?', [hash]).fetchone():
            return await ctx.send(f"This image has already been uploaded!")
        if not imghdr.what('', h=req_data):
            raise Exception

        for i in kws:
            if re.search('[^a-zA-Z ]', i):
                return await ctx.send(f"Invalid keywords!")
        for i in kws:
            if i.lower() not in keywords:
                keywords[i.lower()] = 0
                bot.db.execute('INSERT INTO keywords VALUES (?)', [i.lower()])
            keywords[i.lower()] += 1
        id = bot.db.execute('SELECT COUNT(path) FROM items').fetchone()[0]+1
        with open("images/"+str(id)+"."+imghdr.what('', h=req_data), 'wb') as f:
            f.write(req_data)

        bot.db.execute('INSERT INTO items VALUES (?, ?, 0, ?, ?)', [str(
            id) + '.' + imghdr.what('', h=req_data), ''.join([i.lower()+'|' for i in kws]),  ctx.author.id, hash])
        if bot.db.execute('SELECT COUNT(id) FROM stats WHERE id = ?', [ctx.author.id]).fetchone()[0]:
            bot.db.execute(
                "UPDATE stats SET submitted = submitted + 1 WHERE id = ?", [ctx.author.id])
        else:
            bot.db.execute("INSERT INTO stats VALUES (?, 1, 0)",
                           [ctx.author.id])

        await ctx.send(f"Added for verification (**ID**: {id})")
    except Exception as e:
        print(e)

        await ctx.send("Something went wrong :(")


@commands.is_owner()
@bot.command(description='Save DB', hidden=True)
async def save(ctx):
    bot.db.commit()


@bot.command(description='View your stats!')
async def stats(ctx, user: discord.Member = None):
    user = user or ctx.author
    selected = bot.db.execute(
        'SELECT * FROM stats WHERE id = ?', [user.id]).fetchone()
    if not selected:
        await ctx.reply(f'Submitted = 0, Accepted = 0, Acceptance Rate = -%')
    else:
        await ctx.reply(f'Submitted = {selected[1]}, Accepted = {selected[2]}, Acceptance Rate = {selected[2]*100/selected[1]}%')


@commands.is_owner()
@bot.command(description='Verify', hidden=True)
async def verify(ctx, id, yes: int):
    try:
        if yes:
            bot.db.execute(
                "UPDATE stats SET accepted = accepted + 1 WHERE id IN (SELECT by FROM items WHERE path LIKE '"+id+".%')")

            bot.db.execute(
                "UPDATE items SET verified=1 WHERE path LIKE '"+id+".%'")
            return await ctx.send("Verified!")
        else:
            data = bot.db.execute(
                "SELECT * FROM items WHERE path LIKE '"+id+".%'").fetchone()
            os.remove('images/'+data[0])
            for i in data[1].split('|'):
                if i and keywords[i] == 1:
                    del keywords[i]
                    bot.db.execute('DELETE FROM keywords WHERE name = ?', [i])
            bot.db.execute("DELETE FROM items WHERE path LIKE '"+id+".%'")
    except:
        await ctx.send("Something went wrong :(")


@commands.is_owner()
@bot.command(description='Verifiable', hidden=True)
async def verifiable(ctx: commands.Context):
    embed = discord.Embed(title='Unverified Images', color=0x4287f5)
    for i in bot.db.execute("SELECT * FROM items WHERE verified = 0 LIMIT 25"):
        embed.add_field(name=str(i[0]), value='**By**: '+('<@'+str(i[3])+'>' if i[3]
                        else 'Online')+'\n**Keywords**: '+str(i[1])[:-1].replace('|', ', '), inline=True)
    try:
        await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except:
        await ctx.reply(content="Error using embed! Sent in console")
        for i in bot.db.execute("SELECT * FROM items WHERE verified = 0 LIMIT 25"):
            print(i[0]+'\t\t\t'+i[1])


@tasks.loop(minutes=1)
async def saver():
    bot.db.commit()


@bot.event
async def on_ready():
    try:
        saver.start()
    except:
        pass

asyncio.set_event_loop(asyncio.new_event_loop())
loop = asyncio.get_event_loop()
loop.create_task(bot.start(os.getenv('TOKEN')))
threading.Thread(target=loop.run_forever, daemon=True).start()
