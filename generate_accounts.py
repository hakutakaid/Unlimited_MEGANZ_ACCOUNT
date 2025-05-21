import asyncio
import httpx
import csv
import os
import re
import random
import string
import argparse
from faker import Faker
from datetime import datetime

fake = Faker()

API_BASE = "https://api.mail.tm"

def check_limit(value):
    ivalue = int(value)
    if ivalue <= 8:
        return ivalue
    else:
        raise argparse.ArgumentTypeError("You cannot use more than 8 threads.")

parser = argparse.ArgumentParser(description="Create New Mega Accounts (Async)")
parser.add_argument("-n", "--number", type=int, default=3, help="Number of accounts to create")
parser.add_argument("-t", "--threads", type=check_limit, default=4, help="Max concurrent tasks")
parser.add_argument("-p", "--password", type=str, default=None, help="Password for all accounts")
args = parser.parse_args()

def get_random_string(length=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def extract_urls(text):
    regex = r"https?://[^\s]+"
    return re.findall(regex, text)

async def create_mail_account(client):
    for _ in range(5):
        email = f"{get_random_string(10)}@{(await client.get(f'{API_BASE}/domains')).json()['hydra:member'][0]['domain']}"
        password = get_random_string(12)
        resp = await client.post(f"{API_BASE}/accounts", json={"address": email, "password": password})
        if resp.status_code == 201:
            return email, password
        await asyncio.sleep(1)
    raise Exception("Failed to create Mail.tm account")

async def get_token(client, email, password):
    for _ in range(5):
        resp = await client.post(f"{API_BASE}/token", json={"address": email, "password": password})
        if resp.status_code == 200:
            return resp.json()["token"]
        await asyncio.sleep(1)
    raise Exception("Failed to get Mail.tm token")

async def get_verification_link(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(15):
        resp = await client.get(f"{API_BASE}/messages", headers=headers)
        if resp.status_code == 200 and resp.json()["hydra:member"]:
            msg_id = resp.json()["hydra:member"][0]["id"]
            msg_resp = await client.get(f"{API_BASE}/messages/{msg_id}", headers=headers)
            urls = extract_urls(msg_resp.json().get("text", ""))
            if urls:
                return urls[0]
        await asyncio.sleep(random.randint(3, 5))
    raise Exception("Verification email not found")

async def run_megatools(email, name, password):
    proc = await asyncio.create_subprocess_exec(
        "megatools", "reg", "--scripted", "--register",
        "--email", email, "--name", name, "--password", password,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode()

async def verify_account(cmd_with_link):
    proc = await asyncio.create_subprocess_shell(
        cmd_with_link,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return "registered successfully" in stdout.decode().lower()

async def save_account(email, password, mail_password):
    async with asyncio.Lock():
        async with aiofiles.open("accounts.csv", mode='a') as f:
            await f.write(f"{email},{password},-,{mail_password},-,{datetime.now().isoformat()}\n")

async def create_account(client, semaphore, shared_password=None):
    async with semaphore:
        name = fake.name()
        password = shared_password or get_random_string(12)
        email, mail_password = await create_mail_account(client)
        print(f"[{email}] Creating MEGA account...")

        reg_output = await run_megatools(email, name, password)
        token = await get_token(client, email, mail_password)
        link = await get_verification_link(client, token)

        verify_cmd = reg_output.replace("@LINK@", link)
        verified = await verify_account(verify_cmd)

        if verified:
            print(f"[{email}] Successfully registered and verified.")
            await save_account(email, password, mail_password)
        else:
            print(f"[{email}] Verification failed.")

async def main():
    if not os.path.exists("accounts.csv"):
        with open("accounts.csv", "w") as f:
            f.write("Email,MEGA Password,Usage,Mail.tm Password,Mail.tm ID,Purpose\n")

    semaphore = asyncio.Semaphore(args.threads)
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [create_account(client, semaphore, args.password) for _ in range(args.number)]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    import aiofiles
    asyncio.run(main())