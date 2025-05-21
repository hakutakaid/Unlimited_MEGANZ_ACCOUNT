import os
import re
import csv
import random
import string
import asyncio
import argparse
import pymailtm
import httpx
from pymailtm.pymailtm import CouldNotGetAccountException, CouldNotGetMessagesException
from faker import Faker

fake = Faker()

# Argument parser
def check_limit(value):
    ivalue = int(value)
    if ivalue <= 8:
        return ivalue
    else:
        raise argparse.ArgumentTypeError(f"You cannot use more than 8 threads.")

parser = argparse.ArgumentParser(description="Create New Mega Accounts")
parser.add_argument(
    "-n", "--number", type=int, default=3, help="Number of accounts to create"
)
parser.add_argument(
    "-t", "--threads", type=check_limit, default=None, help="Number of concurrent accounts to create"
)
parser.add_argument(
    "-p", "--password", type=str, default=None, help="Password to use for all accounts"
)
args = parser.parse_args()


def find_url(string):
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    url = re.findall(regex, string)
    return [x[0] for x in url]

def get_random_string(length):
    letters = string.ascii_letters + string.digits
    return "".join(random.choice(letters) for _ in range(length))


class MegaAccount:
    def __init__(self, name, password, client):
        self.name = name
        self.password = password
        self.client = client
        self.email = None
        self.email_id = None
        self.email_password = None
        self.verify_command = None

    async def generate_mail(self):
        mail = pymailtm.MailTm()
        for i in range(5):
            try:
                acc = await mail.get_account(self.client)
            except CouldNotGetAccountException:
                print(f"\r> Could not get new Mail.tm account. Retrying ({i+1} of 5)...", end="\n")
                sleep_output = ""
                for _ in range(random.randint(8, 15)):
                    sleep_output += ". "
                    print("\r"+sleep_output, end="\033[K", flush=True)
                    await asyncio.sleep(1)
            else:
                self.email = acc.address
                self.email_id = acc.id_
                self.email_password = acc.password
                return
        print("\nCould not get account. You are most likely blocked from Mail.tm.")
        print("Please wait 5 minutes and try again with a lower number of accounts/threads.")
        exit()

    async def get_mail(self):
        while True:
            try:
                mail = pymailtm.Account(self.email_id, self.email, self.email_password)
                messages = await mail.get_messages(self.client)
                break
            except (CouldNotGetAccountException, CouldNotGetMessagesException):
                print("> Could not get latest email. Retrying...")
                await asyncio.sleep(random.randint(5, 15))
        if len(messages) == 0:
            return None
        return messages[0]

    def register(self):
        # Registering using megatools subprocess (sync)
        print(f"\r> [{self.email}]: Registering account...", end="\033[K", flush=True)
        import subprocess

        registration = subprocess.run(
            [
                "megatools",
                "reg",
                "--scripted",
                "--register",
                "--email", self.email,
                "--name", self.name,
                "--password", self.password,
            ],
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.verify_command = registration.stdout
        return self.email

    async def verify(self):
        confirm_message = None
        for i in range(5):
            confirm_message = await self.get_mail()
            if confirm_message is not None and "verification required" in confirm_message.subject.lower():
                break
            print(f"\r> [{self.email}]: Waiting for verification email... ({i+1} of 5)", end="\033[K", flush=True)
            await asyncio.sleep(5)

        if confirm_message is None:
            print(f"\r> [{self.email}]: Failed to verify account. No verification email received.", end="\033[K")
            exit()

        links = find_url(confirm_message.text)
        if not links:
            print(f"\r> [{self.email}]: No verification link found in email.", end="\033[K")
            exit()

        self.verify_command = str(self.verify_command).replace("@LINK@", links[0])

        # Run verification command (sync)
        import subprocess
        verification = subprocess.run(
            self.verify_command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )
        if "registered successfully!" in str(verification.stdout):
            print(f"\r> [{self.email}] Successfully registered and verified.", end="\033[K", flush=True)
            print(f"\n{self.email} - {self.password}")

            # Save to CSV
            with open("accounts.csv", "a", newline='') as csvfile:
                csvwriter = csv.writer(csvfile)
                csvwriter.writerow([self.email, self.password, "-", self.email_password, self.email_id, "-"])
        else:
            print("Failed to verify account. Please open an issue on github.")


async def new_account(client):
    if args.password is None:
        password = get_random_string(random.randint(8, 14))
    else:
        password = args.password
    acc = MegaAccount(fake.name(), password, client)
    await acc.generate_mail()
    email = acc.register()
    print(f"\r> [{email}]: Registered. Waiting for verification email...", end="\033[K", flush=True)
    await acc.verify()


async def main():
    # Prepare CSV file
    if not os.path.exists("accounts.csv"):
        with open("accounts.csv", "w") as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(["Email", "MEGA Password", "Usage", "Mail.tm Password", "Mail.tm ID", "Purpose"])

    # Check CSV header
    with open("accounts.csv") as csvfile:
        csvreader = csv.reader(csvfile)
        if next(csvreader) != ["Email", "MEGA Password", "Usage", "Mail.tm Password", "Mail.tm ID", "Purpose"]:
            print("CSV file is not in the correct format. Please use the convert_csv.py script to convert it.")
            exit()

    async with httpx.AsyncClient() as client:
        if args.threads:
            semaphore = asyncio.Semaphore(args.threads)

            async def sem_task():
                async with semaphore:
                    await new_account(client)

            tasks = [sem_task() for _ in range(args.number)]
            await asyncio.gather(*tasks)
        else:
            for _ in range(args.number):
                await new_account(client)


if __name__ == "__main__":
    asyncio.run(main())
