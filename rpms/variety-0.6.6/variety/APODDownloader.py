# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2012, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 3, as published 
# by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

import random
import logging
from variety import Downloader, _str
from variety.Util import Util

logger = logging.getLogger('variety')

random.seed()

class APODDownloader(Downloader.Downloader):
    def __init__(self, parent):
        super(APODDownloader, self).__init__(parent, "apod", "NASA Astro Pic of the Day", "nasa_apod")
        self.queue = []
        self.root = "http://apod.nasa.gov/apod/"

    @staticmethod
    def fetch(url, xml=False):
        return Util.xml_soup(url) if xml else Util.html_soup(url)

    def download_one(self):
        logger.info(lambda: "Downloading an image from NASA's Astro Pic of the Day, " + self.location)
        logger.info(lambda: "Queue size: %d" % len(self.queue))

        if not self.queue:
            self.fill_queue()
        if not self.queue:
            logger.info(lambda: "APOD Queue still empty after fill request - probably nothing more to download")
            return None

        url = self.queue.pop()
        logger.info(lambda: "APOD URL: " + url)

        s = self.fetch(url)
        img_url = None
        try:
            link = s.find("img").parent["href"]
            if link.startswith("image/"):
                img_url = self.root + link
                logger.info(lambda: "Image URL: " + img_url)
        except Exception:
            pass

        if img_url:
            return self.save_locally(url, img_url)
        else:
            logger.info(lambda: "No image url found for this APOD URL")
            return None

    def fill_queue(self):
        logger.info(lambda: "Filling APOD queue from Archive")

        s = self.fetch("http://apod.nasa.gov/apod/archivepix.html")
        urls = [self.root + x["href"] for x in s.findAll("a") if x["href"].startswith("ap") and x["href"].endswith(".html")]
        urls = urls[:730] # leave only last 2 years' pics
        urls = [x for x in urls if x not in self.parent.banned]

        self.queue.extend(urls[:3]) # always append the latest 3
        urls = urls[3:]
        random.shuffle(urls)
        self.queue.extend(urls[:10])
        self.queue = list(reversed(self.queue))

        logger.info(lambda: "APOD queue populated with %d URLs" % len(self.queue))

    def fill_queue_from_rss(self):
        logger.info(lambda: "Filling APOD queue from RSS")

        s = self.fetch(self.location, xml=True)
        urls = [_str(x.find("link").contents[0]) for x in s.findAll("item")]
        urls = [x for x in urls if x not in self.parent.banned]

        self.queue.extend(urls)

        logger.info(lambda: "APOD queue populated with %d URLs" % len(self.queue))