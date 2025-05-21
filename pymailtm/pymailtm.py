import json
import os
import pyperclip
import random
import string
import webbrowser
import asyncio
import httpx

from random_username.generate import generate_username
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List


class Account:
    def __init__(self, id, address, password):
        self.id_ = id
        self.address = address
        self.password = password
        self.api_address = MailTm.api_address

        self.auth_headers = {
            "accept": "application/ld+json",
            "Content-Type": "application/json",
        }

    async def init_token(self, client):
        jwt = await MailTm._make_account_request(client, "token", self.address, self.password)
        self.auth_headers["Authorization"] = f"Bearer {jwt['token']}"

    async def get_messages(self, client: httpx.AsyncClient, page=1):
        r = await client.get(f"{self.api_address}/messages?page={page}", headers=self.auth_headers)
        if r.status_code != 200:
            raise CouldNotGetMessagesException(f"Get message list: HTTP {r.status_code}")

        messages = []
        for message_data in r.json()["hydra:member"]:
            await asyncio.sleep(2)
            r = await client.get(f"{self.api_address}/messages/{message_data['id']}", headers=self.auth_headers)
            if r.status_code != 200:
                raise CouldNotGetMessagesException(f"Get message: HTTP {r.status_code}")

            full = r.json()
            messages.append(Message(
                message_data["id"],
                message_data["from"],
                message_data["to"],
                message_data["subject"],
                message_data["intro"],
                full["text"],
                full["html"],
                message_data
            ))

        return messages

    async def delete_account(self, client):
        r = await client.delete(f"{self.api_address}/accounts/{self.id_}", headers=self.auth_headers)
        return r.status_code == 204

    async def wait_for_message(self, client):
        old_ids = await self._get_existing_messages_id(client)
        while True:
            await asyncio.sleep(2)
            try:
                new_messages = [m for m in await self.get_messages(client) if m.id_ not in old_ids]
                if new_messages:
                    return new_messages[0]
            except CouldNotGetMessagesException:
                continue

    async def _get_existing_messages_id(self, client) -> List[int]:
        while True:
            try:
                messages = await self.get_messages(client)
                return [m.id_ for m in messages]
            except CouldNotGetMessagesException:
                await asyncio.sleep(3)

    async def monitor_account(self, client):
        while True:
            print("\nWaiting for new messages...")
            new_msg = await self.wait_for_message(client)
            print("New message arrived!")
            new_msg.open_web()


@dataclass
class Message:
    id_: str
    from_: Dict
    to: Dict
    subject: str
    intro: str
    text: str
    html: str
    data: Dict

    def open_web(self):
        with NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
            html_content = self.html[0].replace("\n", "<br>").replace("\r", "")
            message = f"""<html>
            <head></head>
            <body>
            <b>from:</b> {self.from_}<br>
            <b>to:</b> {self.to}<br>
            <b>subject:</b> {self.subject}<br><br>
            {html_content}</body>
            </html>"""
            f.write(message)
            f.flush()
            open_webbrowser(f"file://{f.name}")
            asyncio.sleep(1)


def open_webbrowser(link: str) -> None:
    saverr = os.dup(2)
    os.close(2)
    os.open(os.devnull, os.O_RDWR)
    try:
        webbrowser.open(link)
    finally:
        os.dup2(saverr, 2)


class CouldNotGetMessagesException(Exception):
    pass


class CouldNotGetAccountException(Exception):
    pass


class InvalidDbAccountException(Exception):
    pass


class MailTm:
    api_address = "https://api.mail.tm"
    db_file = os.path.join(Path.home(), ".pymailtm")

    async def _get_domains_list(self, client):
        while True:
            r = await client.get(f"{self.api_address}/domains")
            if r.status_code == 200:
                return [x["domain"] for x in r.json()["hydra:member"]]
            await asyncio.sleep(2)

    async def get_account(self, client, password=None):
        username = generate_username(1)[0].lower()
        domain = random.choice(await self._get_domains_list(client))
        address = f"{username}@{domain}"
        if not password:
            password = self._generate_password(6)
        response = await self._make_account_request(client, "accounts", address, password)
        account = Account(response["id"], response["address"], password)
        await account.init_token(client)
        self._save_account(account)
        return account

    @staticmethod
    def _generate_password(length):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    async def _make_account_request(client, endpoint, address, password):
        payload = json.dumps({"address": address, "password": password})
        headers = {
            "accept": "application/ld+json",
            "Content-Type": "application/json"
        }
        r = await client.post(f"{MailTm.api_address}/{endpoint}", data=payload, headers=headers)
        if r.status_code not in [200, 201]:
            raise CouldNotGetAccountException(f"HTTP {r.status_code}")
        return r.json()

    async def monitor_new_account(self, force_new=False):
        async with httpx.AsyncClient() as client:
            account = await self._open_account(client, new=force_new)
            await account.monitor_account(client)

    def _save_account(self, account: Account):
        data = {
            "id": account.id_,
            "address": account.address,
            "password": account.password
        }
        with open(self.db_file, "w+") as db:
            json.dump(data, db)

    def _load_account(self):
        with open(self.db_file, "r") as db:
            data = json.load(db)
        if "address" not in data or "password" not in data or "id" not in data:
            raise InvalidDbAccountException()
        return Account(data["id"], data["address"], data["password"])

    async def _open_account(self, client, new=False):
        async def _new():
            acc = await self.get_account(client)
            print(f"New account created and copied to clipboard: {acc.address}", flush=True)
            return acc

        if new:
            account = await _new()
        else:
            try:
                account = self._load_account()
                await account.init_token(client)
                print(f"Account recovered and copied to clipboard: {account.address}", flush=True)
            except Exception:
                account = await _new()

        try:
            pyperclip.copy(account.address)
        except pyperclip.PyperclipException as e:
            print(e)

        return account

    async def browser_login(self, new=False):
        async with httpx.AsyncClient() as client:
            account = await self._open_account(client, new=new)
            print("\nAccount credentials:")
            print(f"\nEmail: {account.address}")
            print(f"Password: {account.password}\n")
            open_webbrowser("https://mail.tm/")
            await asyncio.sleep(1)