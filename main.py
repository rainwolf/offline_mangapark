import asyncio
import random
import aiohttp
import docker
import bs4, re, requests, os
from pandas.io.clipboard import clipboard_get
from time import sleep
from random import randint


# get content from clipboard
clipboard = clipboard_get()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"
}


def get_user_agent_and_cookies(url="https://mangapark.org"):
    try:
        with requests.Session() as session:
            response = session.post(
                "http://localhost:8000/bypass-cloudflare",
                headers={"Content-Type": "application/json"},
                data=f'{{"url": "{url}"}}',
            )
            response_json = response.json()
            print(response_json)
            return response_json["user_agent"], response_json["cookies"]
    except Exception as e:
        print(f"{url}\nError getting user agent and cookies: {e}")
        sleep(randint(1, 3))
        return get_user_agent_and_cookies(url=url)
        

async def download(
    url, i, total_images, session, c, comic_title, chapter_title, total_chapters, semaphore
):
    print(
        f"Chapter: {c} of {total_chapters}: Downloading image {i} of {total_images}..."
    )
    async with semaphore:
        try:
            async with session.get(url, headers=headers) as response:
                file = await response.read()
                ext = url[-5:]
                if ext[0] != ".":
                    ext = ext[1:]
                # filename = url.split("/")[-1]
                with open(
                    f"../{comic_title}/{c:05} {comic_title} - {chapter_title} - {i:05}{ext}",
                    "wb",
                ) as f:
                    f.write(file)
        except Exception as e:
            print(
                f"Error downloading image {i} of {total_images} in chapter {c} of {total_chapters}: {e}, retrying..."
            )
            await asyncio.sleep(random.randint(1, 3))
            await download(
                url, i, total_images, session, c, comic_title, chapter_title, total_chapters
            )


async def download_chapter(chapter_url, c, comic_title, total_chapters, user_agent, cookies):
    chapter_page_source = requests.get(chapter_url, headers={"User-Agent": user_agent}, cookies=cookies).text
    soup = bs4.BeautifulSoup(chapter_page_source, "html.parser")
    chapter_title = soup.find("title").text.replace(
        " - Share Any Manga on MangaPark", ""
    )
    print(f"Downloading chapter {c} of {total_chapters}: {chapter_title}...")
    image_urls = re.findall(r"https?://[^\"]+/media/[^\"]+", chapter_page_source)

    def f7(seq):
        seen = set()
        seen_add = seen.add
        return [x for x in seq if not (x in seen or seen_add(x))]

    image_urls = f7(image_urls)
    semaphore = asyncio.Semaphore(10)
    async with aiohttp.ClientSession() as session:
        tasks = []
        i = 0
        total = len(image_urls)
        for img_url in image_urls:
            i += 1
            tasks.append(
                download(
                    img_url,
                    i,
                    total,
                    session,
                    c,
                    comic_title,
                    chapter_title,
                    total_chapters,
                    semaphore,
                )
            )
        await asyncio.gather(*tasks)


async def main():
    site_url = "https://mangapark.org"
    user_agent, cookies = get_user_agent_and_cookies(url=clipboard)
    comic_source = requests.get(
        clipboard, headers={"User-Agent": user_agent}, cookies=cookies
    ).text
    print(f"Fetching comic information from {clipboard}...")
    print(f"{comic_source=}")
    soup = bs4.BeautifulSoup(comic_source, "html.parser")
    comic_title = soup.find("title").text.replace(" - Share Any Manga on MangaPark", "")
    # make folder with title
    os.makedirs(f"../{comic_title}", exist_ok=True)
    print(f"Downloading {comic_title}...")

    comic_prefix = clipboard.replace("https://mangapark.org", "")
    chapters_pattern = re.compile(rf"{comic_prefix}/\d+[^\"]+")
    chapter_suffixes = re.findall(chapters_pattern, comic_source)
    chapter_suffixes = sorted(list(set(chapter_suffixes)))
    chapter_urls = [site_url + suffix for suffix in chapter_suffixes]
    print(f"Found {len(chapter_urls)} chapters to download.")

    async with aiohttp.ClientSession() as session:
        tasks = []
        i = 0
        total_chapters = len(chapter_urls)
        for chapter_url in chapter_urls:
            i += 1
            tasks.append(download_chapter(chapter_url, i, comic_title, total_chapters, user_agent, cookies))
        await asyncio.gather(*tasks)
    print(f"Finished downloading {comic_title}.")

container = None
try:
    client = docker.DockerClient(base_url='unix://var/run/docker.sock')
    client.images.pull("frederikuni/docker-cloudflare-bypasser:latest")
    container = client.containers.run("frederikuni/docker-cloudflare-bypasser:latest", detach=True, ports={'8000/tcp': 8000})
    with asyncio.Runner() as runner:
        runner.run(main())
finally:
    container.stop()
    container.remove()