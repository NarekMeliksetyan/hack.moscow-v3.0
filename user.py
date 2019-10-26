import json

class User:

	def __init__(self, name, age, country):
		self.name = name
		self.age = age
		self.country = country

	def print_user(self):
		print("My name is " + name)
		print("I am " + age + " years old")
		print("I am from " + country)

class Ru_users:

	def __init__(self):
		self.number = 0
		self.users = list()

	def add_user(self, user):
		self.number += 1
		self.users.append(user)
	
	def del_user(self, user):
		self.number -= 1
		self.users.remove(user)

	def print_users(self):
		i = 0
		for us in self.users:
			i += 1
			print('User no ' + str(i) + ';')
			us.print_user()
			print()

n = int(input())
ru_users = Ru_users()

while n:
	n -= 1
	name = input()
	age = input()
	country = input()
	
	user = User(name, age, country)
	ru_users.add_user(user)
	print()

ru_users.print_users()
