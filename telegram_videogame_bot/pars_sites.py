import requests
from bs4 import BeautifulSoup

def fetch_news(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Проверяем ответ сервера

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('article', class_='sc-1pw4fyi-6')

        news_list = []
        for article in articles:
            link_element = article.find('a', class_='sc-1out364-0')
            if link_element and 'href' in link_element.attrs:
                title = link_element.get('title', 'No title provided')
                link = link_element['href']
                news_list.append((title, link))

        return news_list
    except requests.RequestException as e:
        print(f"Ошибка при запросе к {url}: {e}")
        return []

def display_news(news_list):
    if not news_list:
        print("Новости не найдены.")
    else:
        for title, link in news_list:
            print(f"{title}\nСсылка: {link}\n")

url = 'https://kotaku.com/culture/news'
news = fetch_news(url)
display_news(news)