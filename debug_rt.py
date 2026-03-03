import requests
from bs4 import BeautifulSoup
import re

def debug_page(url):
    print(f'\n{"="*60}\n{url}\n{"="*60}')
    r = requests.get(url, timeout=15, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    soup = BeautifulSoup(r.text, 'html.parser')

    # score-board check
    sb = soup.find('score-board') or soup.find('score-board-deprecated')
    print('score-board:', dict(sb.attrs) if sb else 'NOT FOUND')

    # rt-text with % and their parents
    print('\nrt-text with scores:')
    for el in soup.find_all('rt-text'):
        text = el.get_text(strip=True)
        if re.search(r'\d+%|^--$', text):
            parent = el.parent
            gp = parent.parent if parent else None
            gp_class = str(gp.get('class', ''))[:60] if gp else ''
            gp_tag = gp.name if gp else ''
            print(f'  text={text:8s} parent={str(parent.name):25} gp_tag={gp_tag:20} gp_class={gp_class}')

    # data-qa score elements
    print('\ndata-qa score elements:')
    for el in soup.find_all(attrs={'data-qa': re.compile('tomatometer|audience|score', re.I)}):
        print(f'  data-qa={el.get("data-qa"):45s} text={el.get_text(strip=True)[:30]}')

debug_page('https://www.rottentomatoes.com/m/the_matrix')
debug_page('https://www.rottentomatoes.com/m/love_solutions')
