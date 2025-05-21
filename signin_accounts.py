import csv
import asyncio


async def check_account(email, password):
    # Jalankan megatools secara async
    process = await asyncio.create_subprocess_exec(
        "megatools", "ls", "-u", email, "-p", password,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if b"/Root" in stdout:
        print(f"\r> [{email}]: Successfully logged in", end="\033[K", flush=True)
    else:
        print(f"\r> [{email}]: ERROR", end="\033[K\n", flush=True)


async def main():
    tasks = []
    # Baca file CSV
    with open("accounts.csv") as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            if not row or row[0] == "Email":
                continue

            email = row[0].strip()
            password = row[1].strip()

            task = asyncio.create_task(check_account(email, password))
            tasks.append(task)
            await asyncio.sleep(1)  # jeda antara pembuatan task, bukan blocking

    # Tunggu semua task selesai
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
