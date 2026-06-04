import time
from typing import Tuple, Coroutine, Any

# from pyppeteer import launch

from utils.img import encoding2url


def parse_cookie(cookie_str: str) -> list[dict]:
    cookies = []
    for item in cookie_str.split(';'):
        key, val = item.strip().split('=')
        cookies.append({
            "name": key,
            "value": val,
            "domain": '.ainvest.com',
            "path": '/',
            "expires": time.time() + 3600 * 1000,
        })
    return cookies


temp_cookie = ('other_uid=ths_wencai_international_pc_robot_db7a740ec3da2d066f4fe9758ab947d1; '
               '_ga=GA1.1.498626245.1741871777; '
               'voiceStatus=open; '
               'csrf_token=1d64239c-b5aa-47c9-836d-658419c208a0; '
               '_clck=jusslm%7C2%7Cfwt%7C0%7C1898; '
               'user_status=0; '
               'ticket=1a9300c0daa98e3758427b704487be57; '
               'escapename=lh1741918195841; '
               'u_name=lh1741918195841; '
               'userid=1803262958; '
               'user=MDpsaDE3NDE5MTgxOTU4NDE6Ok5vbmU6NTAwOjE4MTMyNjI5NTg6Ojo6OjE4MDMyNjI5NTg6MTc1MDA1MzMyNjo6OjE3NDAwMT'
               'czNDg6MjY3ODQwMDowOjFmZmU4YmY0NjBmNDljMWViYzE0MTVjOTE2Mzc2MzYzMTo6MA%3D%3D; '
               'sessionid=10a1149a85faf08211099f434cbfe83e0; '
               '_clsk=2zcofv%7C1750061625616%7C1%7C1%7Cd.clarity.ms%2Fcollect; '
               '_ga_DRJEHTT060=GS2.1.s1750061624$o35$g1$t1750062029$j55$l0$h0')


# async def browser_screenshot(url: str,
#                              viewport: tuple[int, int],
#                              exec_path: str = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
#                              proxy: str = 'http://localhost:8899'
#                              ) -> str:
#     browser = await launch(executablePath=exec_path, args=[f'--proxy-server={proxy}'], headless=False)
#     page = await browser.newPage()
#     print(f'Get screenshot of {url}')
#     await page.setCookie(*parse_cookie(temp_cookie))
#     time.sleep(1)
#     await page.goto(url, {"waitUntil": "networkidle2"})
#     await page.setViewport({"width": viewport[0], "height": viewport[1]})
#     time.sleep(1)
#     img_buffer = await page.screenshot({'encoding': 'base64'})
#     await browser.close()
#     img_src = img_buffer
#     return encoding2url(img_src)
