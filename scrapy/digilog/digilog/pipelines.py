# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

import re
from urllib3.util import parse_url
from w3lib.url import canonicalize_url
import logging

logger = logging.getLogger(__name__)


def normalize_url(s: str) -> str:
    try:
        url = parse_url(s)
        path = '' if url.path is None else re.sub(r'/\Z', '', url.path)
        query = '' if url.query is None else '?{}'.format(url.query)
        without_protocol = ''.join([
            url.host,
            re.sub(r'/\Z', '', path),
            query
        ])
        return canonicalize_url(without_protocol)
    except Exception as e:
        logger.exception('Unable to normalize input URL {}'.format(s))
        return s


class SimplePipeline:
    def __init__(self):
        self.crawl_id = None
        self.url_dict = {}

    def open_spider(self, spider):
        url = normalize_url(spider.url)
        self.crawl_id = spider.ds.postgres.insert_crawl(url)
        logger.info("Inserted new crawl with ID: {}".format(self.crawl_id))
        head_id = spider.ds.postgres.insert_first_result_record(self.crawl_id, url)
        self.url_dict[url] = head_id
        if spider.queue_entry is not None:
            spider.ds.postgres.insert_queue_crawl_connection(spider.queue_entry.id, self.crawl_id)

    def process_item(self, item, spider):
        url = normalize_url(item['url'])
        links = item['links']
        if url in self.url_dict:
            parent_id = self.url_dict[url]
        else:
            logger.warning("WARNING: Parent URL not found: {} in {}".format(url, self.url_dict))
            parent_id = None
        mongo_id = spider.ds.mongodb.insert_crawl_result(self.crawl_id, parent_id, item['html'], item['raw_text'])
        spider.ds.postgres.update_mongo_id(parent_id, str(mongo_id))
        children = spider.ds.postgres.insert_child_links(self.crawl_id, parent_id, links, normalize_url)
        self.url_dict.update(children)