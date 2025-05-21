import asyncio
import signal
import sys
from argparse import ArgumentParser
from .pymailtm_async import MailTmAsync


def handle_exit(sig, frame):
    print("\n\nClosing! Bye!")
    sys.exit(0)


def setup_signal():
    signal.signal(signal.SIGINT, handle_exit)


async def main():
    setup_signal()

    parser = ArgumentParser(
        description="Async interface to mail.tm web API. Temp email address will be printed."
    )
    parser.add_argument('-n', '--new-account', action='store_true',
                        help="Force creation of a new account")
    parser.add_argument('-l', '--login', action='store_true',
                        help="Print the credentials and exit")
    args = parser.parse_args()

    mailtm = MailTmAsync()
    if args.login:
        account = await mailtm.get_account()
        print("\nAccount credentials:")
        print(f"Email: {account.address}")
        print(f"Password: {account.password}\n")
    else:
        account = await mailtm.get_account()
        print(f"Monitoring account: {account.address}")
        print("Waiting for new messages...")
        while True:
            messages = await account.get_messages()
            if messages:
                msg = messages[0]
                print(f"\nNew message from {msg.from_['address']} with subject '{msg.subject}'")
                print(msg.text)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
