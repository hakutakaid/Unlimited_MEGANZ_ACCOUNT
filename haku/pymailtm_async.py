import asyncio
import httpx
import json
import os
import random
import string
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Dict, List


class CouldNotGetMessagesException(Exception):
    pass


class CouldNotGetAccountException(Exception):
    pass


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


class MailTmAsync:
    api_address = "https://api.mail.tm"
    db_file = os.path.join(Path.home(), ".pymailtm")

    @staticmethod
    async def _make_account_request(endpoint, address, password):
        async with httpx.AsyncClient() as client:
            payload = {"address": address, "password": password}
            headers = {
                "accept": "application/ld+json",
                "Content-Type": "application/json"
            }
            resp = await client.post(f"{MailTmAsync.api_address}/{endpoint}",
                                     content=json.dumps(payload), headers=headers)
            if resp.status_code not in [200, 201]:
                raise CouldNotGetAccountException(f"HTTP {resp.status_code}")
            return resp.json()

    async def _get_domains_list(self):
        async with httpx.AsyncClient() as client:
            while True:
                r = await client.get(f"{self.api_address}/domains")
                if r.status_code == 200:
                    domains = [x["domain"] for x in r.json()["hydra:member"]]
                    return domains
                await asyncio.sleep(2)

    async def get_account(self, password=None):
        from random_username.generate import generate_username
        username = generate_username(1)[0].lower()
        domain = random.choice(await self._get_domains_list())
        address = f"{username}@{domain}"
        if not password:
            password = self._generate_password(6)
        response = await self._make_account_request("accounts", address, password)
        return self.Account(response["id"], response["address"], password)

    @staticmethod
    def _generate_password(length):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    class Account:
        def __init__(self, id_, address, password):
            self.id_ = id_
            self.address = address
            self.password = password

        async def _get_token(self):
            return await MailTmAsync._make_account_request("token", self.address, self.password)

        async def get_messages(self, page=1):
            token = await self._get_token()
            headers = {
                "accept": "application/ld+json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token['token']}"
            }
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{MailTmAsync.api_address}/messages?page={page}", headers=headers)
                if r.status_code != 200:
                    raise CouldNotGetMessagesException(f"Get message list: HTTP {r.status_code}")

                messages = []
                for msg in r.json()["hydra:member"]:
                    await asyncio.sleep(2)
                    full_msg = await client.get(f"{MailTmAsync.api_address}/messages/{msg['id']}", headers=headers)
                    if full_msg.status_code != 200:
                        raise CouldNotGetMessagesException(f"Get message: HTTP {full_msg.status_code}")

                    msg_json = full_msg.json()
                    messages.append(Message(
                        id_=msg["id"],
                        from_=msg["from"],
                        to=msg["to"],
                        subject=msg["subject"],
                        intro=msg["intro"],
                        text=msg_json["text"],
                        html=msg_json["html"],
                        data=msg
                    ))

                return messages
