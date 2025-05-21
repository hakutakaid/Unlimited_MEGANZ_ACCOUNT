import asyncio
import csv
import os
import random
import re
import string
from faker import Faker
import httpx
import subprocess
from pymailtm_async import MailTmAsync, CouldNotGetAccountException, CouldNotGetMessagesException

fake = Faker()

API = "https://api.mail.tm"


def find_url(string):
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?\u00ab\u00bb“”‘’]))"
    url = re.findall(regex, string)
    return [x[0] for x in url]


def get_random_string(length):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))


class MegaAccountAsync:
    def __init__(self, name, password):
        self.name = name
        self.password = password

    async def generate_mail(self):
        mail = MailTmAsync()
        for i in range(5):
            try:
                acc = await mail.get_account()
                break
            except CouldNotGetAccountException:
                print(f"Could not get Mail.tm account. Retrying {i+1}/5")
                await asyncio.sleep(random.randint(8, 15))
        else:
            print("Mail.tm block detected. Exiting.")
            raise Exception("Mail.tm blocked")

        self.email = acc.address
        self.email_id = acc.id_
        self.email_password = acc.password

    async def get_mail(self):
        mail = MailTmAsync.Account(self.email_id, self.email, self.email_password)
        while True:
            try:
                messages = await mail.get_messages()
                break
            except (CouldNotGetMessagesException, CouldNotGetAccountException):
                print(f"{self.email}: Waiting for message...")
                await asyncio.sleep(random.randint(5, 15))

        return messages[0] if messages else None

    async def register(self):
        await self.generate_mail()
        print(f"[{self.email}]: Registering account")
        self.verify_command = None

        proc = await asyncio.create_subprocess_exec(
            "megatools", "reg", "--scripted", "--register",
            "--email", self.email,
            "--name", self.name,
            "--password", self.password,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        self.verify_command = stdout.decode()

    async def verify(self):
        for i in range(5):
            msg = await self.get_mail()
            if msg and "verification required" in msg.subject.lower():
                break
            print(f"[{self.email}]: Waiting verification mail ({i+1}/5)")
            await asyncio.sleep(5)
        else:
            print(f"{self.email}: No verification email found.")
            return

        links = find_url(msg.text)
        if not links:
            print(f"{self.email}: No link found in verification mail.")
            return

        self.verify_command = self.verify_command.replace("@LINK@", links[0])

        verify_proc = await asyncio.create_subprocess_shell(
            self.verify_command,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await verify_proc.communicate()

        if "registered successfully!" in stdout.decode():
            print(f"[{self.email}] Registered successfully")
            self.save()
        else:
            print(f"[{self.email}] Verification failed")

    def save(self):
        with open("accounts.csv", "a", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([self.email, self.password, "-", self.email_password, self.email_id, "-"])


async def new_account(password):
    name = fake.name()
    acc = MegaAccountAsync(name, password)
    await acc.register()
    await acc.verify()


async def main(n, password=None):
    if not os.path.exists("accounts.csv"):
        with open("accounts.csv", "w", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Email", "MEGA Password", "Usage", "Mail.tm Password", "Mail.tm ID", "Purpose"])

    tasks = []
    for _ in range(n):
        pw = password or get_random_string(random.randint(8, 14))
        tasks.append(new_account(pw))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", type=int, default=3)
    parser.add_argument("-p", "--password", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.number, args.password))
