# download.py

import itertools
import os
import shutil
import sys
from urllib.parse import urlparse

import pandas as pd

import urllib3
from urllib3.util import Retry
from urllib3.exceptions import HTTPError


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

classes = ["cat", "fish"]
set_types = ["train", "test", "val"]


def download_image(url: str, filename: str) -> tuple[int, str]:
    res = 0, None
    if not os.path.exists(filename):
        try:
            http = urllib3.PoolManager(retries=Retry(connect=1, read=1, redirect=2))
            with http.request("GET", url, preload_content=False) as resp, open(
                filename, "wb"
            ) as out_file:
                if resp.status == 200:
                    shutil.copyfileobj(resp, out_file)
                else:
                    res = 1, resp.status
            resp.release_conn()
        except (HTTPError, ConnectionError):
            res = 1, "connection error"
        except Exception as e:
            res = 1, e
    return res


def main() -> int:
    input_file = "images.csv"
    good_file = "images.good.csv"
    bad_file = "images.bad.csv"
    if not os.path.exists(input_file):
        print(f'File "{input_file}" not found')
        return -1

    good_header = "url,class,type\n" if not os.path.exists(good_file) else None
    bad_header = "url,class,type,error\n" if not os.path.exists(bad_file) else None
    good_fd = open(good_file, "a", encoding="utf-8")
    bad_fd = open(bad_file, "a", encoding="utf-8")
    if good_header:
        good_fd.write(good_header)
    if bad_header:
        bad_fd.write(bad_header)

    # get args and create output directory
    imagesDF = pd.read_csv(input_file)

    for set_type, klass in list(itertools.product(set_types, classes)):
        path = f"./{set_type}/{klass}"
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"Created directory {path}")

    print(f"Downloading {len(imagesDF)} images:")

    good_cnt = 0
    bad_cnt = 0
    for url, klass, data_type in zip(
        imagesDF["url"], imagesDF["class"], imagesDF["type"]
    ):
        basename = os.path.basename(urlparse(url).path)
        filename = f"{data_type}/{klass}/{basename}"
        res, err = download_image(url, filename)
        if res:
            print(f"Error {err} downloading {url} to {os.path.dirname(filename)}")
            bad_fd.write(f'{url},{klass},{data_type},"{err}"\n')
            bad_cnt += 1
        else:
            good_fd.write(f"{url},{klass},{data_type}\n")
            good_cnt += 1
        if good_cnt % 50 == 0 or (bad_cnt and bad_cnt % 20 == 0):
            print(f"... downloaded {good_cnt}, {bad_cnt} failed ...")

    bad_fd.close()
    good_fd.close()
    print()
    print(f"DONE. Downloaded {good_cnt} files. Error downloading {bad_cnt} files.")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc != 0:
        sys.exit(rc)
