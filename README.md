# CosmoPawn

An alternative to [ImageNet](https://image-net.org)

## How to use it?
You need to create a bot in the [Discord Developer Applications Portal](https://discord.com/developers/applications) and get the token

Create a file called `.env`

Add to the file, the following files
```
TOKEN=<the bot token from step 1>
```

Assuming, you have Python and PIP installed, run the following commands
```sh
python -m pip install -r requirements.txt
waitress-serve 'bot:flask_app'
```


