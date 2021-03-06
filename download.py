import os, argparse, time, json, glob, copy
from os.path import join
import multiprocessing as mp

from scrapers import *

parser = argparse.ArgumentParser()
parser.add_argument("url_file", type=str)
parser.add_argument("--save_output", action='store_true', default=False)
parser.add_argument("--output_dir", type=str, default="scraped")
parser.add_argument("--n_threads", type=int, default=1)
parser.add_argument("--max_urls", type=int, default=-1)
parser.add_argument("--chunk_size", type=int, default=100)
parser.add_argument("--scraper", type=str, default="newspaper")
parser.add_argument("--compress", action='store_true', default=False)
args = parser.parse_args()

def init_output_dirs(output_dir):
    s = copy.deepcopy(os.path.basename(args.url_file))
    if '.bz2' in s:
        chunk_dir = s[:s.find('.bz2')]
    elif '.xz' in s:
        chunk_dir = s[:s.find('.xz')]
    else:
        chunk_dir = s
    chunk_path = os.path.join(output_dir, chunk_dir)
    data_path = os.path.join(chunk_path, 'data')
    meta_path = os.path.join(chunk_path, 'meta')
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    if not os.path.exists(meta_path):
        os.makedirs(meta_path)
    return chunk_dir, chunk_path, data_path, meta_path

def get_completed_fids(data_path, meta_path):
    parsed_fid, meta_fid = set(), set()
    for ff in glob.glob(join(data_path, '*.txt')):
        parsed_fid.add(int(os.path.split(ff)[-1].split("-")[0]))
    for ff in glob.glob(join(meta_path, '*.json')):
        meta_fid.add(int(os.path.split(ff)[-1].split("-")[0]))
    return parsed_fid.intersection(meta_fid)

def load_urls(completed_fids):
    with open(args.url_file) as fh:
        url_entries = [
            (fid, url) for (fid, url) in enumerate(fh) if fid not in completed_fids
        ]
        if args.max_urls != -1:
            url_entries = url_entries[: args.max_urls]
    return url_entries

def vet_link(link):
    # checks link type and status
    # returns if a non-200 status code or
    # the link points to a non-html file
    try:
        info = urlopen(link)
        link_type = info.headers["Content-Type"]
        link_status = info.status
    except:
        link_type = None

    # we want "text/html" only!
    is_good_link = False
    try:
        if ('text/html' in link_type and 
            link_status == 200):
            is_good_link = True
    except:
        pass

    return is_good_link, link_type

def download(url_entry, 
             scraper=args.scraper, 
             save_output=args.save_output):

    uid, url = url_entry
    url = url.strip()
    
    # is_good_link, link_type = vet_link(url)

    # if not is_good_link:
    #     return

    # choose scraper and scrape
    if scraper == "bs4":
        scrape = bs4_scraper
    elif scraper == "newspaper":
        scrape = newspaper_scraper
    elif scraper == "raw":
        scrape = raw_scraper
    text, meta = scrape(url)

    if text is None or text.strip() == "":
        return

    if args.save_output:
        fid = "{:07d}-{}".format(uid, hash(url.encode()))
        parsed_fp = join(data_path, "{}.txt".format(fid))
        meta_fp = join(meta_path, "{}.json".format(fid))

        with open(parsed_fp, "w") as out:
            out.write(text)
        with open(meta_fp, "w") as out:
            json.dump(meta, out)

    return text

if __name__ == "__main__":

    if args.save_output:
        chunk_dir, chunk_path, data_path, meta_path = init_output_dirs(args.output_dir)

    completed_fids = get_completed_fids(data_path, meta_path)
    url_entries = load_urls(completed_fids)

    def chunks(l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    for c, chunk in enumerate(chunks(url_entries, args.chunk_size)):
        
        # set up worker pool
        p = mp.Pool(args.n_threads)

        print("Downloading chunk {}".format(c+1))
        t1 = time.time()

        # # iterating will be needed to dump larger files later
        # scraped = []
        # for result in p.imap(download, url_entries):
        #     # problem links return None instead of content
        #     if result != None:
        #         scraped.append(result)
        data = list(p.imap(download, chunk))

        total_time = time.time() - t1

        print("Chunk time: ", str(total_time), " seconds", '\n')

    # save xz file to massively reduce file size
    # this will take a long time for recent reddit months
    if args.compress:
        print('Compressing...')
        out_arch = join('../', '../', chunk_dir+'.xz')
        os.system('cd ' + data_path + ' && tar cfJ ' + out_arch + ' *.txt')

    print("Done!")