# download.py

import os
import sys
from urllib.parse import urlparse

import pandas as pd
import aiohttp
import asyncio
import aiofiles
from aiohttp import ClientSession
from aiohttp.connector import TCPConnector

classes = ["cat", "fish"]
set_types = ["train", "test", "val"]


async def download_image(
    session: ClientSession, url: str, filename: str, queue: asyncio.Queue
) -> None:
    res = 0, None
    if not os.path.exists(filename):
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(filename, "wb") as out_file:
                        await out_file.write(await resp.read())
                else:
                    res = 1, resp.status
        except (aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
            res = 1, e
        except Exception as e:
            res = 1, e
    await queue.put((url, filename, res))


async def worker(
    session: ClientSession, queue: asyncio.Queue, result_queue: asyncio.Queue
):
    while True:
        url, klass, data_type = await queue.get()
        if url is None:
            break
        basename = os.path.basename(urlparse(url).path)
        filename = f"{data_type}/{klass}/{basename}"
        await download_image(session, url, filename, result_queue)
        queue.task_done()


async def process_results(result_queue: asyncio.Queue, good_fd, bad_entries):
    good_cnt = 0
    bad_cnt = 0
    while True:
        url, filename, (res, err) = await result_queue.get()
        if url is None:
            break
        if res:
            print(f"Error {err} downloading {url} to {os.path.dirname(filename)}")
            bad_entries.append(f'{url},{klass},{data_type},"{err}"\n')
            bad_cnt += 1
        else:
            await good_fd.write(f"{url},{klass},{data_type}\n")
            good_cnt += 1
        if good_cnt % 50 == 0 or (bad_cnt and bad_cnt % 20 == 0):
            print(f"... downloaded {good_cnt}, {bad_cnt} failed ...")
        result_queue.task_done()


async def download_images(
    image_list, good_file, bad_file, good_file_exists, existing_bad_entries
):
    connector = TCPConnector(limit_per_host=3)
    async with ClientSession(connector=connector) as session:
        good_header = "url,class,type\n" if not good_file_exists else None
        bad_entries = existing_bad_entries

        async with aiofiles.open(good_file, "a", encoding="utf-8") as good_fd:
            if good_header:
                await good_fd.write(good_header)

            queue = asyncio.Queue()
            result_queue = asyncio.Queue()

            for url, klass, data_type in image_list:
                await queue.put((url, klass, data_type))

            workers = [
                asyncio.create_task(worker(session, queue, result_queue))
                for _ in range(10)
            ]
            result_processor = asyncio.create_task(
                process_results(result_queue, good_fd, bad_entries)
            )

            await queue.join()
            for _ in range(10):
                await queue.put((None, None, None))

            await result_queue.join()
            await result_queue.put((None, None, (0, None)))

            await asyncio.gather(*workers)
            await result_processor


def read_existing_bad_entries(bad_file):
    if os.path.exists(bad_file):
        with open(bad_file, "r", encoding="utf-8") as file:
            return file.readlines()
    return []


def main() -> int:
    input_file = "images.csv"
    good_file = "images.good.csv"
    bad_file = "images.bad.csv"
    if not os.path.exists(input_file):
        print(f'File "{input_file}" not found')
        return -1

    good_file_exists = os.path.exists(good_file)
    existing_bad_entries = read_existing_bad_entries(bad_file)

    imagesDF = pd.read_csv(input_file)

    for set_type, klass in list(itertools.product(set_types, classes)):
        path = f"./{set_type}/{klass}"
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"Created directory {path}")

    print(f"Downloading {len(imagesDF)} images:")

    image_list = list(zip(imagesDF["url"], imagesDF["class"], imagesDF["type"]))

    try:
        asyncio.run(
            download_images(
                image_list, good_file, bad_file, good_file_exists, existing_bad_entries
            )
        )
    except KeyboardInterrupt:
        print("Download interrupted by user.")
        return -1

    if existing_bad_entries:
        with open(bad_file, "a", encoding="utf-8") as bad_fd:
            bad_fd.writelines(existing_bad_entries)

    print("DONE. All images processed.")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc != 0:
        sys.exit(rc)
