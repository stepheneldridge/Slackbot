import json
import logging
import logging.config
import math
import re
import time
from decimal import Decimal
from slackclient import SlackClient

AUTH_FILE = "bot.auth"

logging.config.fileConfig('log.conf')
logger = logging.getLogger(__name__)
bot_token = None
with open(AUTH_FILE, 'r') as f:
	bot_token = f.read().strip()
CLIENT = SlackClient(bot_token)
RTM_READ_DELAY = 1
COMMAND_TRIGGERS = {"do", "who", "leave", "say", "tell", "annoy", "calc", "pizza", "store", "save"}
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"
USER_REGEX = "<@(|[WU].+?)>"


class SlackBot(object):
	def __init__(self, client):
		self.client = client
		self.annoyee = None
		self.calculator = Calculator(logger.warning)
		try:
			self.load()
		except:
			logger.info("No Data File")
		if self.client.rtm_connect(with_team_state=False):
			logger.info("Connected")
			self.running = True
			self.bot_id = self.api_call("auth.test")["user_id"]
			self.getUsers()
		else:
			logger.error("Failed to connect")

	def api_call(self, *args, **kwargs):
		if "text" in kwargs:
			logger.debug("RESPONSE - %s" % kwargs["text"])
		response = self.client.api_call(*args, **kwargs)
		if response["ok"] is False:
			logger.error(response["error"])
			return {}
		return response

	def getUsers(self):
		users_list = self.api_call("users.list")
		self.users = {}
		if "members" in users_list:
			for member in users_list["members"]:
				self.users[member["id"]] = member["profile"]["display_name"] or member["profile"]["real_name"] or member["name"]
		else:
			logger.error("Could not load users")

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
				event["text"] = event["text"].replace("&gt;", ">")
				user_id, message = self.parseMention(event["text"])
				logger.debug("%s - %s" % (self.users[event["user"]], event["text"]))
				if user_id == self.bot_id:
					return message, event["channel"]
				elif event["user"] == self.annoyee:
					return "say {}".format(event["text"]), event["channel"]
			elif event["type"] == "error":
				logger.warning(event["msg"])
		return None, None

	def handleResponse(self, command, params):
		if command == "do":
			return "I will not do {}".format(params)
		elif command == "who":
			return "I don't know"
		elif command == "leave":
			self.running = False
			return "Goodbye"
		elif command == "say":
			return params
		elif command == "tell":
			user_id, message = self.parseMention(params)
			if user_id not in self.users:
				return "I don't know who that is"
			if not message:
				return "I can't tell someone nothing"
			channel = self.getIM(user_id)
			if channel is not None:
				self.api_call("chat.postMessage", channel=channel, text=message)
			return None
		elif command == "annoy":
			if params.startswith("stop"):
				self.annoyee = None
				return "Fine"
			user_id = re.search(USER_REGEX, params).group(1)
			if user_id not in self.users:
				return "I don't know who that is"
			self.annoyee = user_id
			return "Okay"
		elif command == "calc":
			return self.calculator.calculate(params)  # self.calculate(params)
		elif command == "store":
			if len(params) > 0 and params[0].isalpha():
				if getattr(self, "last_answer", None) is None:
					return "No value to store"
				self.stored[params[0].upper()] = str(self.last_answer)
				return "{} stored in {}".format(self.last_answer, params[0].upper())
			else:
				return "Invalid store"
		elif command == "pizza":
			try:
				return self.handlePizza(params)
			except:
				return "Invalid pizza commands"
		elif command == "save":
			self.save()
			return "Save successful"

	def save(self):
		data = {
			"pizzas": getattr(self, "pizzas", {}),
			"stored": getattr(self, "stored", {})
		}
		with open("data.json", "w+") as out:
			json.dump(data, out)
			logger.info("Save Successful")

	def load(self):
		with open("data.json", "r") as data:
			file_data = json.load(data)
			self.pizzas = file_data.get("pizzas", {})
			self.stored = file_data.get("stored", {})
			logger.info("Load Successful")

	def handlePizza(self, input):
		if not hasattr(self, "pizzas"):
			self.pizzas = {}
		params = input.split()
		user_id = re.search(USER_REGEX, params[1]).group(1) if len(params) > 1 else None
		if params[0] == "set":
			if user_id in self.users:
				self.pizzas[user_id] = int(params[2])
				return "{0} now has {1} pizza{2}".format(params[1], params[2], "s" if int(params[2]) is not 1 else "")
			else:
				return "Unknown user: {}".format(params[1])
		elif params[0] == "list":
			output = ""
			for i, v in self.pizzas.items():
				output += "<@{0}> has {1} pizza{2}\n".format(i, v, "s" if v is not 1 else "")
			return output if output is not "" else "No one has pizzas"
		elif params[0] == "forget":
			if user_id in self.users and user_id in self.pizzas:
				del self.pizzas[user_id]
			return "<@{}> has been forgotten".format(user_id)
		elif params[0] == "add":
			if user_id in self.users:
				if user_id in self.pizzas:
					self.pizzas[user_id] += 1
				else:
					self.pizzas[user_id] = 1
				return "{0} now has {1} pizza{2}".format(params[1], self.pizzas[user_id], "s" if self.pizzas[user_id] is not 1 else "")
			else:
				return "Unknown user: {}".format(params[1])


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
			try:
				response = self.handleResponse(cmd, params)
			except Exception as e:
				logger.debug(e)
				response = type(e)
		if response is not None:
			self.api_call("chat.postMessage", channel=channel, text=response)

	def infixToPostfix(self, input):
		level = {"^": 4, "*": 3, "/": 3, "%": 3, "+": 2, "-": 2, "(": 1}
		prefixUnary = math.__dict__
		prefixUnary["abs"] = abs
		stack = []
		postfixList = []
		for i in input:
			if i == 'pi':
				i = str(math.pi)
			elif i == 'e':
				i = str(math.e)
			elif i == 'phi':
				i = str((1 + math.sqrt(5)) / 2)
			elif i == 'ans':
				i = str(getattr(self, "last_answer", 0))
			elif len(i) == 1 and i.isalpha() and i.isupper():
				i = str(self.stored.get(i, 0))
			if i == '(':
				stack.append(i)
			elif i == ')':
				top = stack.pop()
				while top != '(':
					postfixList.append(top)
					top = stack.pop()
				if len(stack) > 0 and stack[-1] in prefixUnary:
					postfixList.append(stack.pop())
			elif i in prefixUnary:
				stack.append(i)
			elif len(i) > 1 or i[0].isdigit() or i == "!":
				postfixList.append(i)
			elif i == '':
				continue
			else:
				while len(stack) > 0 and level.get(stack[-1], 1) >= level.get(i, 1):
					postfixList.append(stack.pop())
				stack.append(i)
		while len(stack) > 0:
			postfixList.append(stack.pop())
		return postfixList

	def calculate(self, input):
		reg = r'((?:(?<!\d)(?<!\d\s)\-)?\d*[\.,]?\d+(?:[Ee][\+\-]\d+)?|\w+|\S)'
		matches = re.findall(reg, re.sub('\s+', ' ', input).strip())
		logger.debug(matches)
		postfix = self.infixToPostfix(matches)
		logger.debug(postfix)
		stack = []
		for i in postfix:
			try:
				a = Decimal(i.replace(",", "."))
				stack.append(a)
			except:
				if len(stack) < 1:
					return "Too many operators"
				c = 0
				b = stack.pop()
				if i is '!':
					c = math.factorial(b)
				elif i in math.__dict__:
					c = Decimal(math.__dict__[i](b))
				elif i is 'abs':
					c = abs(b)
				elif len(stack) == 0 and i is '-':
					c = -b
				else:
					if len(stack) < 1:
						return "Too many operators"
					a = stack.pop()
					if i is '+':
						c = a + b
					elif i is '-':
						c = a - b
					elif i is '*':
						c = a * b
					elif i is '/':
						c = a / b
					elif i is '^':
						c = a ** b
					elif i is '%':
						c = a % b
					else:
						return "Invalid operation: {}".format(i)
				stack.append(c)
		if math.isclose(stack[-1] % 1, 0, abs_tol=10**-15):
			stack[-1] = math.floor(stack[-1])
		elif math.isclose(stack[-1] % 1, 1, abs_tol=10**-15):
			stack[-1] = math.ceil(stack[-1])
		self.last_answer = stack[-1]
		return str(self.last_answer)


class Calculator(object):
	def __init__(self, logger):
		self.functions = {i: v for i,v in math.__dict__.items() if not i.startswith('_')}
		self.functions['abs'] = abs
		self.functions["~"] = Calculator.negate
		self.functions["clear"] = self.clear_store
		self._logger = logger
		self.ans = None
		self.stored = {}

	def log_message(self, message, mtype="TEST"):
		self._logger("%s - %s" % (mtype, message))

	def calculate(self, text):
		temp = self.parse(text)
		self.log_message(temp)
		if temp is not []:
			self.ans = self._calculate(self.infixToPostfix(temp))
			return self.ans
		return None

	@staticmethod
	def negate(x):
		return -x

	def clear_store(self, x):
		if x in self.stored:
			del self.stored[x]
		return 0

	def infixToPostfix(self, input):
		level = {"->": 5, "^": 4, "*": 3, "/": 3, "%": 3, "+": 2, "-": 2, "(": 1}
		stack = []
		postfixList = []
		for i in input:
			if i == 'pi':
				i = str(math.pi)
			elif i == 'e':
				i = str(math.e)
			elif i == 'phi':
				i = str((1 + math.sqrt(5)) / 2)
			elif i == 'ans':
				i = str(self.ans if self.ans else 0)
			if i == '(':
				stack.append(i)
			elif i == ')':
				top = stack.pop()
				while top != '(':
					postfixList.append(top)
					top = stack.pop()
				if len(stack) > 0 and stack[-1] in self.functions:
					postfixList.append(stack.pop())
			elif i in self.functions:
				stack.append(i)
			elif i not in level and (len(i) > 1 or i[0].isdigit() or i == "!" or i.isupper()):
				postfixList.append(i)
			elif i == '':
				continue
			else:
				while len(stack) > 0 and (level.get(stack[-1], 1) >= level.get(i, 1) or stack[-1] in self.functions):
					postfixList.append(stack.pop())
				stack.append(i)
		while len(stack) > 0:
			postfixList.append(stack.pop())
		self.log_message(postfixList)
		return postfixList

	def _calculate(self, postfix):
		stack = []
		for i in postfix:
			try:
				if len(i) == 1 and i.isupper():
					a = i
				else:
					a = Decimal(i)
				stack.append(a)
			except:
				if len(stack) < 1:
					return "Too many operators"
				c = 0
				b = stack.pop()
				if i is '!':
					c = math.factorial(b)
				elif i in self.functions:
					c = Decimal(self.functions[i](b))
				else:
					if len(stack) < 1:
						return "Too many operators"
					a = stack.pop()
					if i == '->':
						if type(b) is str:
							self.stored[b] = a
						c = a
					else:
						if a in self.stored:
							a = self.stored[a]
						if b in self.stored:
							b = self.stored[b]
						if i is '+':
							c = a + b
						elif i is '-':
							c = a - b
						elif i is '*':
							c = a * b
						elif i is '/':
							c = a / b
						elif i is '^':
							c = a ** b
						elif i is '%':
							c = a % b
						else:
							return "Invalid operation: {}".format(i)
				stack.append(c)
		if stack[-1] in self.stored:
			stack[-1] = self.stored[stack[-1]]
		if isinstance(stack[-1], Decimal):
			if math.isclose(stack[-1] % 1, 0, abs_tol=10**-15):
				stack[-1] = math.floor(stack[-1])
			elif math.isclose(stack[-1] % 1, 1, abs_tol=10**-15):
				stack[-1] = math.ceil(stack[-1])
		return stack[-1]

	def parse(self, text):
		buffer = ""
		out_list = []
		for i in text:
			if i in ['\n','\t',' ','\r']:
				out_list.append(buffer)
				buffer = ""
			elif buffer is "":
				buffer += i;
			elif buffer is "-":
				if i is ">":
					out_list.append("->")
					buffer = ""
				elif len(out_list) > 0 and (out_list[-1][0].isalnum() or out_list[-1][0] in ".)") and out_list[-1] not in self.functions:
					out_list.append(buffer)
					buffer = i
				elif i.isdigit() or i is ".":
					out_list.append("~")
					buffer = i
				elif i is "-":
					if len(out_list) > 0 and (out_list[-1][0].isalnum() or out_list[-1][0] in ".)") and out_list[-1] not in self.functions:
						buffer = "+"
					else:
						buffer = ""
				elif i is "+":
					pass
				else:
					out_list.append("~") # negative
					buffer = i
			elif i in "1234567890.":
				if buffer[0].isalnum() or buffer[0] in ".-":
					buffer += i
				else:
					out_list.append(buffer)
					buffer = i
			elif i.isalpha():
				if buffer.isalnum():
					buffer += i
				else:
					out_list.append(buffer)
					buffer = i
			else:
				out_list.append(buffer)
				buffer = i
		out_list.append(buffer)
		return out_list


if __name__ == "__main__":
	bot = SlackBot(CLIENT)
	try:
		while bot.running:
			bot.read()
			time.sleep(RTM_READ_DELAY)
	except KeyboardInterrupt:
		logger.info("Stopped in Terminal")
	finally:
		bot.save()
	logger.info("Bot has stopped")