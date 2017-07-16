"""
    pipe file collected from 4chan to stdout
"""
import json
import os
import time
import requests
from pprint import pprint


class ChanPiper:

    def __init__(self, keyword, input_file_types, input_boards, input_refresh_rate):
        self.keyword = keyword
        self.file_types = input_file_types
        self.pending = []
        self.processing = None
        self.finished = []
        self.failed = []
        self.boards = input_boards
        self.refresh_rate = input_refresh_rate

    def start(self):
        while True:
            self.collect()
            time.sleep(self.refresh_rate)

    def collect(self):
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)\
         AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

        for board in self.boards:
            for page_num in range(1, 11):
                page_data = requests.get('https://a.4cdn.org/{}/{}.json'.format(board, page_num), headers=headers)
                page_data = json.loads(page_data.content.decode('utf-8'))
                threads = page_data["threads"]
                for thread in threads:
                    qualified = False
                    op = thread["posts"][0]
                    # check title and op name
                    if self.keyword in (op['name'] + op['semantic_url']):
                        qualified = True
                    # check comment section if there are comments
                    if "com" in op:
                        if self.keyword in op["com"]:
                            qualified = True
                    if qualified:
                        thread_data = requests.get("https://a.4cdn.org/{}/thread/{}.json".format(board, op["no"]),
                                                   headers=headers)
                        thread_response = json.loads(thread_data.content.decode('utf-8'))
                        # posts is a list of posts
                        posts = thread_response["posts"]
                        # post is a dict with info about each post
                        for post in posts:
                            if "ext" in post and post["ext"][1:] in self.file_types:
                                # pprint(post)
                                # print("----")
                                download_link = "https://i.4cdn.org/{}/{}{}".format(board, post["tim"], post["ext"])
                                self.pending.append(download_link)
                                print(download_link)
                    # pprint(thread["posts"][0])

x = ChanPiper("ygyl", ["webm"], ["wsg"], 9999)
x.start()
