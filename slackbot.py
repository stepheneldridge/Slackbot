import time
import re
from slackclient import SlackClient

AUTH_FILE = "bot.auth"

bot_token = None
with open(AUTH_FILE, 'r') as f:
	bot_token = f.read().strip()
CLIENT = SlackClient(bot_token)
RTM_READ_DELAY = 1
COMMAND_TRIGGERS = {"do", "who", "leave", "say", "tell"}
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"
USER_REGEX = "<@(|[WU].+?)>"


class SlackBot(object):
	def __init__(self, client):
		self.client = client
		if self.client.rtm_connect(with_team_state=False):
			print("Connected")
			self.running = True
			self.bot_id = self.api_call("auth.test")["user_id"]
			self.getUsers()
		else:
			print("Failed to connect")

	def api_call(self, *args, **kwargs):
		if "text" in kwargs:
			print("RESPONSE:", kwargs["text"])
		response = self.client.api_call(*args, **kwargs)
		if response["ok"] is False:
			print("ERROR:", response["error"])
			return {}
		return response

	def getUsers(self):
		users_list = self.api_call("users.list")
		self.users = {}
		if "members" in users_list:
			for member in users_list["members"]:
				self.users[member["id"]] = member["name"]
		else:
			print("Could not load users")

	def read(self):
		command, channel = self.parseCommand(self.client.rtm_read())
		if command:
			self.handleCommand(command, channel)

	def parseMention(self, message):
		matches = re.search(MENTION_REGEX, message)
		return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

	def parseCommand(self, events):
		for event in events:
			if event["type"] == "message" and not "subtype" in event:
				user_id, message = self.parseMention(event["text"])
				if user_id == self.bot_id:
					return message, event["channel"]
			else:
				pass
		return None, None

	def handleResponse(self, command, params):
		if command == "do":
			return "I will not do {}".format(params)
		if command == "who":
			return "I don't know"
		if command == "leave":
			self.running = False
			return "Goodbye"
		if command == "say":
			return params
		if command == "tell":
			user_id, message = self.parseMention(params)
			if user_id in self.users and message:
				channel = self.getIM(user_id)
				if channel is not None:
					self.api_call("chat.postMessage", channel=channel, text=message)
				return None
			else:
				return "I don't know who that is"

	def getIM(self, user_id):
		im = self.api_call("im.open", user=user_id)
		if "channel" in im:
			return im["channel"]["id"]
		return None

	def formatResponse(self, response):
		pass

	def handleCommand(self, command, channel):
		response = None
		split = command.split(" ", 1)
		cmd = split[0].lower() if len(split) > 0 else None
		params = split[1] if len(split) > 1 else None
		if cmd in COMMAND_TRIGGERS:
			response = self.handleResponse(cmd, params)
		if response is not None:
			self.api_call("chat.postMessage", channel=channel, text=response)

if __name__ == "__main__":
	bot = SlackBot(CLIENT)
	while bot.running:
		bot.read()
		time.sleep(RTM_READ_DELAY)
	print("Bot has stopped")