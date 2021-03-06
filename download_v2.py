from __future__ import print_function
import os
import argparse
import time
import json
import os.path as op
import tarfile
from glob import glob
from hashlib import md5

from multiprocessing import Pool

# for backward compatibility
from six.moves.urllib.request import urlopen

from scrapers import bs4_scraper, newspaper_scraper, raw_scraper

parser = argparse.ArgumentParser()
parser.add_argument("url_file", type=str)
parser.add_argument("--save_output", action="store_true", default=False)
parser.add_argument("--output_dir", type=str, default="scraped")
parser.add_argument("--n_threads", type=int, default=1)
parser.add_argument("--max_urls", type=int, default=-1)
parser.add_argument("--chunk_size", type=int, default=100)
parser.add_argument("--scraper", type=str, default="newspaper")
parser.add_argument("--compress", action="store_true", default=False)
parser.add_argument("--compress_fmt", type=str, default="xz")
args = parser.parse_args()


def init_output_dirs(url_file, base_dir):
    cid = op.split(url_file)[-1]
    for fmt in [".bz2", ".xz", ".gz"]:
        cid = cid[: cid.find(fmt)] if fmt in cid else cid

    data_dir = mkdir(op.join(base_dir, "data", cid))
    meta_dir = mkdir(op.join(base_dir, "meta", cid))
    mkdir(op.join(base_dir, "archive"))
    return cid, data_dir, meta_dir


def get_completed_fids(data_dir, meta_dir):
    parsed_fid, meta_fid = set(), set()
    for ff in glob(op.join(data_dir, "*.txt")):
        parsed_fid.add(int(op.split(ff)[-1].split("-")[0]))
    for ff in glob(op.join(meta_dir, "*.json")):
        meta_fid.add(int(op.split(ff)[-1].split("-")[0]))
    return parsed_fid.intersection(meta_fid)


def load_urls(url_file, completed_fids, max_urls=-1):
    with open(url_file) as fh:
        url_entries = [
            (fid, url) for (fid, url) in enumerate(fh) if fid not in completed_fids
        ]
        if max_urls != -1:
            url_entries = url_entries[:max_urls]
    return url_entries


def vet_link(link):
    # check if server responds with non-200 status code or link points to a
    # non-html file
    link_type, link_status = "", -1
    try:
        info = urlopen(link)
        link_type = info.headers["Content-Type"]
        link_status = info.status
    except:
        pass

    # we want "text/html" only!
    is_good_link = False
    if "text/html" in link_type and link_status == 200:
        is_good_link = True

    return is_good_link, link_type


def download(url_entry, scraper=args.scraper, save_output=args.save_output):
    uid, url = url_entry
    url = url.strip()

    # is_good_link, link_type = vet_link(url)
    # if not is_good_link:
    #     return

    if scraper == "bs4":
        scrape = bs4_scraper
    elif scraper == "newspaper":
        scrape = newspaper_scraper
    elif scraper == "raw":
        scrape = raw_scraper

    text, meta = scrape(url)
    if text is None or text.strip() == "":
        return

    if save_output:
        fid = "{:07d}-{}".format(uid, md5(url.encode()).hexdigest())
        parsed_fp = op.join(data_dir, "{}.txt".format(fid))
        meta_fp = op.join(meta_dir, "{}.json".format(fid))
        with open(parsed_fp, "w") as out:
            out.write(text)
        with open(meta_fp, "w") as out:
            json.dump(meta, out)

    return text


def create_archive(cid, out_dir, fmt):
    if fmt not in ["xz", "bz2", "gz"]:
        raise Exception('Compression format must be "xz", "bz2", or "gz"')

    data_dir = op.join(out_dir, "data", cid)
    meta_dir = op.join(out_dir, "meta", cid)
    data_tar = op.join(out_dir, "archive", "{}_data.{}".format(cid, fmt))
    meta_tar = op.join(out_dir, "archive", "{}_meta.{}".format(cid, fmt))

    t1 = time.time()
    print("Compressing...")
    with tarfile.open(data_tar, "w:" + fmt) as tar:
        tar.add(data_dir, arcname="{}_data".format(cid))

    with tarfile.open(meta_tar, "w:" + fmt) as tar:
        tar.add(meta_dir, arcname="{}_meta".format(cid))

    print("Tarballs created in {} seconds\n".format(time.time() - t1))
    return data_tar, meta_tar


#######################################################################
#                           Util functions                            #
#######################################################################


def extract_archive(archive_fp, outdir="."):
    with tarfile.open(archive_fp, "r") as tar:
        tar.extractall(outdir)
    return outdir


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i : i + n]


def mkdir(fp):
    if not op.exists(fp):
        os.makedirs(fp)
    return fp


if __name__ == "__main__":
    completed_fids = set()
    meta_dir, data_dir, = ".", "."

    if args.save_output:
        cid, data_dir, meta_dir = init_output_dirs(args.url_file, args.output_dir)
        completed_fids = get_completed_fids(data_dir, meta_dir)

    url_entries = load_urls(args.url_file, completed_fids, args.max_urls)
    for c, chunk in enumerate(chunks(url_entries, args.chunk_size)):
        print("Downloading chunk {}".format(c + 1))
        t1 = time.time()
        p = Pool(args.n_threads)
        data = list(p.imap(download, chunk))
        print("Chunk time: {} seconds\n".format(time.time() - t1))

    # this takes a long time for recent reddit months
    if args.save_output and args.compress:
        create_archive(cid, args.output_dir, args.compress_fmt)

    print("Done!")
