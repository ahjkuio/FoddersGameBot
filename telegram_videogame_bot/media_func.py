import requests
from bs4 import BeautifulSoup

def news_kotaku():
    url = "https://kotaku.com/culture/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('article', class_='sc-1pw4fyi-6')

        news_list = []
        for article in articles:
            link_element = article.find('a', class_='sc-1out364-0')
            image_element = article.find('img')
            if link_element and 'href' in link_element.attrs:
                title = link_element.get('title', 'No title provided')
                link = link_element['href']
                image_url = image_element['src'] if image_element else None
                news_list.append((title, link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

def news_gamesradar():
    url = "https://www.gamesradar.com/news/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('div', class_='listingResult')

        news_list = []
        for article in articles:
            link_element = article.find('a', class_='article-link')
            image_element = article.find('figure', class_='article-lead-image-wrap')
            if link_element and 'href' in link_element.attrs:
                title = link_element.get('aria-label', 'No title provided')
                link = link_element['href']
                image_url = image_element['data-original'] if image_element else None
                news_list.append((title, link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

def news_polygon():
    url = "https://www.polygon.com/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('div', class_='c-entry-box--compact', limit=10)

        news_list = []
        for article in articles:
            link_element = article.find('a', class_='c-entry-box--compact__image-wrapper')
            title_element = article.find('h2', class_='c-entry-box--compact__title').find('a')
            
            # Ищем изображение внутри тега <noscript>
            noscript_element = article.find('noscript')
            image_element = None
            if noscript_element:
                noscript_soup = BeautifulSoup(noscript_element.decode_contents(), 'html.parser')
                image_element = noscript_soup.find('img')
          
            if image_element:
                image_url = image_element.get('src')

            if link_element and title_element and image_url:
                title = title_element.get_text().strip()
                link = link_element['href']
                news_list.append((title, link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

import requests
from bs4 import BeautifulSoup

def news_ixbt():
    url = "https://ixbt.games/news/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://ixbt.games/'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('div', class_='card card-widget border-xs-none', limit=10)

        news_list = []
        for article in articles:
            # Извлекаем URL статьи из атрибута onclick
            onclick_attr = article.find('div', class_='card-image-background')['onclick']
            link = onclick_attr.split("'")[1] if onclick_attr else None

            # Извлекаем URL изображения
            image_element = article.find('img')
            image_url = image_element['src'] if image_element and 'src' in image_element.attrs else None

            # Извлекаем заголовок статьи
            title_element = article.find('a', class_='card-link')
            title = title_element.get_text().strip() if title_element else None

            if link and title and image_url:
                full_link = f"https://ixbt.games{link}"
                news_list.append((title, full_link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []
    

def news_rockpapershotgun():
    url = "https://www.rockpapershotgun.com/news"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find('ul', class_='summary_list').find_all('li', limit=10)

        news_list = []
        for article in articles:
            link_element = article.find('a', class_='link--expand')
            image_element = article.find('img', class_='thumbnail_image')
            title_element = link_element


            if image_element:
                image_url = image_element['src']

            if link_element and title_element and image_url:
                title = title_element.get_text().strip()
                link = link_element['href']
                news_list.append((title, link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

import requests
from bs4 import BeautifulSoup

def news_gamespot():
    url = "https://www.gamespot.com/news/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Список для хранения новостей
        news_list = []

        # Извлечение новостей из первого раздела
        first_section = soup.find('section', class_='promo--container')
        if first_section:
            articles = first_section.find_all('a', limit=10)
            for article in articles:
                link_element = article
                image_element = article.find('img')
                title_element = article.find('h2')

                if link_element and 'href' in link_element.attrs:
                    link = link_element['href']
                    title = title_element.get_text().strip() if title_element else "No title"
                    
                    if image_element and 'src' in image_element.attrs:
                        image_url = image_element['src']
                    else:
                        image_url = None

                    if image_url and image_url.startswith('http'):
                        news_list.append((title, link, image_url))

        # Извлечение новостей из второго раздела
        second_section = soup.find('section', class_='promo-strip--grid--quarter')
        if second_section:
            articles = second_section.find_all('a', limit=10-len(news_list))
            for article in articles:
                link_element = article
                image_element = article.find('img')
                title_element = article.find('h3', class_='media-title')

                if link_element and 'href' in link_element.attrs:
                    link = link_element['href']
                    title = title_element.get_text().strip() if title_element else "No title"
                    
                    if image_element and 'src' in image_element.attrs:
                        image_url = image_element['src']
                    else:
                        image_url = None

                    if image_url and image_url.startswith('http'):
                        news_list.append((title, link, image_url))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

if __name__ == "__main__":
    news_items = news_gamespot()
    for title, link, image_url in news_items:
        print(f"Title: {title}\nLink: {link}\nImage URL: {image_url}\n")