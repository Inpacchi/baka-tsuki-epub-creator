from errno import ENOTDIR
from glob import glob
from os import path, listdir, mkdir
from shutil import copy, copytree, copyfileobj
from re import sub

from bs4 import BeautifulSoup
from ebooklib import epub
from requests import get
from PIL import Image


# Global Constants
TITLE = None
BULLET_HEADER = '<p style="text-align: center; font-size: 300%; text-indent: 0;">•</p>\n'
HEADERS = ('School_Rules', 'Prologue', 'Chapter', 'Afterword', 'Notes')


# Global Variables
page_index = 1


# To-Do List
# TODO: Check newer volume and page parsing
# Might be able to use sets of page numbers and set global constants accordingly

# Main method
def run(url):
    page_soup = BeautifulSoup(get(url).content, 'html.parser')

    initialize(url)
    download_pre_chapter_images(page_soup)

    headers = find_headers(page_soup)
    for index, _ in enumerate(headers):
        try:
            chapter_downloader(headers[index], headers[index + 1])
        except IndexError:
            chapter_downloader(headers[index])
    create_book()


def initialize(url):
    global TITLE
    TITLE = url.split('title=')[1].replace(':', '_')

    global page_index
    page_index = 1

    if not path.exists('output'):
        mkdir('output')

    if not path.exists(f'{TITLE}'):
        mkdir(f'{TITLE}')

    if not path.exists(f'{TITLE}/src'):
        mkdir(f'{TITLE}/src')

    if not path.exists(f'{TITLE}/src/images'):
        mkdir(f'{TITLE}/src/images')


def download_pre_chapter_images(page_soup):
    image = page_soup.find('ul').find_next()

    while image is not None:
        title = sub(r'[\\/:*"<>+|.%$^&£\n?\']', '', image.find_all('div')[3].text)

        if not 'Title Page' == title and 'Page' in title:
            image = None
            break

        image_tag = image.find('a')['href']
        try:
            page_number = image_tag.split('_')[1].split('.')[0]
        except IndexError:
            try:
                page_number = image_tag.split('-')[2].split('.')[0]
            except IndexError:
                page_number = image_tag.split('-')[1].split('.')[0]

        if page_number == 'cover':
            title = 'Cover'
        elif page_number in '0000a':
            title = 'Front_and_Back_Cover'
        elif page_number in ('0000b', '0000c'):
            title = f'Installation_pn-{page_number}'
        elif page_number in '0001':
            title = 'Title_Page'
        elif title in ('Table of Content', 'Table of Contents'):
            title = f'Table_of_Contents_pn-{page_number}'
        else:
            title = f'{title.replace(" ", "_")}_pn-{page_number}'

        create_image_html(download_image(image), title, True)
        image = image.find_next_sibling()


def chapter_downloader(chapter, next_chapter=None):
    title = chapter.find('span').attrs['id'].split(':')[0]
    html = []
    part_index = 1

    if 'Notes' in title:
        return

    if any(header_id in title for header_id in ('Afterword', 'School_Rules')):
        chapter = chapter.find_next_sibling()
        while True:
            if chapter == next_chapter or chapter is None:
                break
            html.append(chapter)
            chapter = chapter.find_next_sibling()

        create_chapter_html(title, html)
        return

    create_image_html(download_image(chapter.find_next_sibling()), f'{title}_Title')
    chapter = chapter.find_next_sibling().find_next_sibling()
    while True:
        if chapter == next_chapter:
            if html[len(html) - 1] == BULLET_HEADER:
                html.pop()
            break
        elif chapter is None:
            break

        if chapter.name == 'div' and chapter.find('a') is not None:
            try:
                if chapter.find('a')['class'][0] == 'image':
                    create_chapter_html(f'{title}_Part_{part_index}', html)
                    create_image_html(download_image(chapter), title)
                    part_index += 1
                    html = []
            except KeyError:
                pass
        elif '<br/>' in str(chapter):
            html.append(BULLET_HEADER)
        else:
            html.append(chapter)

        chapter = chapter.find_next_sibling()

    if part_index > 1:
        create_chapter_html(f'{title}_Part_{part_index}', html)
    else:
        create_chapter_html(title, html)


def download_image(block):
    for a_tag_1 in block.find_all('a', href=True):
        image_url = BeautifulSoup(get(f'https://baka-tsuki.org{a_tag_1["href"]}').content, 'html.parser')
        for a_tag_2 in image_url.find_all('a', href=True):
            if all(selector in a_tag_2['href'] for selector in ['project', 'images']):
                image_name = a_tag_2['href'].split('/')[5]
                image_path = f'{TITLE}/src/images/{image_name}'
                if not path.exists(image_path):
                    image_bytes = get(f'https://baka-tsuki.org{a_tag_2["href"]}', stream=True)
                    if image_bytes.status_code == 200:
                        image_bytes.raw.decode_content = True
                        with open(image_path, 'wb') as image_stream:
                            copyfileobj(image_bytes.raw, image_stream)
                return image_path


def find_headers(page_soup):
    h2_blocks = page_soup.find_all('h2')
    section_blocks = []
    for h2_block in h2_blocks:
        span_block = h2_block.find('span')
        if span_block is not None and span_block.attrs is not None \
                and any(header_id in span_block.attrs['id'] for header_id in HEADERS):
            section_blocks.append(h2_block)
    return section_blocks


def create_chapter_html(title, html):
    point_allocation_tag = None
    for line in html:
        if 'Point Allocation (' in str(line):
            point_allocation_tag = 'Point Allocation ('
            break

    global page_index
    file_path = f'{TITLE}/src/{format(page_index, "03")}_{title}.xhtml'
    if not path.exists(file_path):
        with open(file_path, 'w+', encoding='utf-8') as html_file:
            html_file.write('<?xml version="1.0" encoding="utf-8"?>\n')
            html_file.write('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink">\n')
            html_file.write('  <head>\n')
            html_file.write(f'    <title>{TITLE} - {title}</title>\n')
            html_file.write('    <link href="stylesheet.css" rel="stylesheet" type="text/css"/>\n')
            html_file.write('  </head>\n')
            html_file.write('  <body>\n')

            if title in ('Afterword', 'School_Rules'):
                html_file.write(f'    <h2>{title.replace("_", " ")}</h2>\n')

            if point_allocation_tag is not None:
                html_file.write('    <center>\n')

            for line in html:
                line = str(line).replace('\n', '')
                if '<sup class=' in line:
                    starting_index = line.find('<sup class=')
                    ending_index = line.find('</sup>') + 6
                    line = line[0:starting_index] + line[ending_index:]

                if point_allocation_tag is not None:
                    if point_allocation_tag in line:
                        html_file.write(f'      {line}\n    </center>\n')
                        point_allocation_tag = None
                    else:
                        html_file.write(f'      {line}\n')
                else:
                    html_file.write(f'    {line}\n')
            html_file.write('  </body>\n')
            html_file.write('</html>\n')
            page_index += 1


def create_image_html(image_path, image_title, switch=False):
    if image_title == 'Cover':
        return

    image_name = str(image_path.split('images')[1]).strip('/')
    if switch:
        file_name = f'{image_title}.xhtml'
    else:
        try:
            page_number = image_name.split('_')[1].split('.')[0].strip('/')
        except IndexError:
            try:
                page_number = image_name.split('-')[2].split('.')[0].strip('/')
            except IndexError:
                page_number = image_name.split('-')[1].split('.')[0].strip('/')

        file_name = f'{image_title}_Image_{page_number}.xhtml'

    global page_index
    file_path = f'{TITLE}/src/{format(page_index, "03")}_{file_name}'
    page_index += 1

    if not path.exists(file_path):
        with open(file_path, mode='w+') as image_html_file:
            image = Image.open(f'{TITLE}/src/images/{image_name}')
            image_html_file.write('<?xml version="1.0" encoding="utf-8"?>\n')
            image_html_file.write('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink">\n')
            image_html_file.write('  <head>\n')
            if image_title == 'Cover':
                image_html_file.write(f'    <title>{TITLE} - {image_title}</title>\n')
            else:
                image_html_file.write(f'    <title>{TITLE} - {image_title} - {image_name}</title>\n')
            image_html_file.write('  </head>\n')
            image_html_file.write('  <body>\n')
            image_html_file.write('    <div style="text-align: center; padding: 0pt; margin: 0pt;">\n')
            image_html_file.write('      <svg xmlns="http://www.w3.org/2000/svg" '
                                  'xmlns:xlink="http://www.w3.org/1999/xlink" height="100%" '
                                  'preserveAspectRatio="xMidYMid meet" version="1.1" '
                                  f'viewBox="0 0 {image.size[0]} {image.size[1]}" width="100%">\n')
            image_html_file.write(f'        <image width="{image.size[0]}" height="{image.size[1]}" '
                                  f'xlink:href="{image_name}"/>\n')
            image_html_file.write('      </svg>\n')
            image_html_file.write('    </div>\n')
            image_html_file.write('  </body>\n')
            image_html_file.write('</html>\n')


def copy_static_files(book):
    stylesheet_src = 'static_files/stylesheet'
    stylesheet_dest = f'{TITLE}/src/stylesheet'

    fonts_src = 'static_files/fonts'
    fonts_dest = f'{TITLE}/src/fonts'

    try:
        copytree(stylesheet_src, stylesheet_dest)
        copytree(fonts_src, fonts_dest)
    except OSError as e:
        if e.errno == ENOTDIR:
            copy(stylesheet_src, stylesheet_dest)
            copy(fonts_src, fonts_dest)

    with open(f'{stylesheet_dest}/stylesheet.css', 'r') as stylesheet:
        book.add_item(epub.EpubItem(uid='stylesheet',
                                    file_name='stylesheet.css',
                                    media_type='text/css',
                                    content=stylesheet.read()))

    with open(f'{fonts_dest}/DejaVuSerif.ttf', 'rb') as font:
        book.add_item(epub.EpubItem(uid='DejaVu-Serif',
                                    file_name='DejaVuSerif.ttf',
                                    media_type='application/vnd.ms-opentype',
                                    content=font.read()))

    with open(f'{fonts_dest}/DejaVuSerifCondensed-Bold.ttf', 'rb') as font:
        book.add_item(epub.EpubItem(uid='DejaVu-Serif-Condensed-Bold',
                                    file_name='DejaVuSerifCondensed-Bold.ttf',
                                    media_type='application/vnd.ms-opentype',
                                    content=font.read()))

    with open(f'{fonts_dest}/DejaVuSerif-Italic.ttf', 'rb') as font:
        book.add_item(epub.EpubItem(uid='DejaVu-Serif-Italic',
                                    file_name='DejaVuSerif-Italic.ttf',
                                    media_type='application/vnd.ms-opentype',
                                    content=font.read()))


def create_book(title=None):
    book = epub.EpubBook()
    if title is not None:
        global TITLE
        TITLE = title
    volume = str(TITLE.split('_')[2])

    # Epub Metadata
    book.set_title(f'Kyoukai Senjou no Horizon {volume}')
    book.add_author('Minoru Kawakami', 'author', 'aut', 'author')
    book.add_author('Satoyasu', 'illustrator', 'ill', 'illustrator')
    book.set_language('en')
    book.set_identifier(TITLE)

    # Populate Epub with content
    populate_epub(book)
    copy_static_files(book)

    # Add navigation details to Epub
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Create Epub
    epub.write_epub(f'output/{TITLE}.epub', book)


def populate_epub(book):
    image_file_path = f'{TITLE}/src/images'
    html_file_path = f'{TITLE}/src'

    image_list = sorted(listdir(image_file_path))
    xhtml_list = sorted(glob(f'{html_file_path}/*.xhtml'))

    global page_index
    page_index = 1

    for image in image_list:
        try:
            title = image.split('_')[1]
        except IndexError:
            try:
                title = image.split('-')[2]
            except IndexError:
                title = image.split('-')[1]
        title = title.strip('.jpg')

        if title.lower() == 'cover':
            book.set_cover(image, open(f'{image_file_path}/{image}', 'rb').read())
            book.spine.append('cover')
        else:
            book.add_item(epub.EpubItem(uid=image,
                                        file_name=image,
                                        media_type='image/jpeg',
                                        content=open(f'{image_file_path}/{image}', 'rb').read()
                                        ))

    insert_last = []
    illustration_index = 1

    for xhtml in xhtml_list:
        xhtml = xhtml.split('/')[2]
        title = xhtml.strip(f'format({page_index}, "03")_').strip('.xhtml').replace('_', ' ')

        if 'pn-' in title:
            starting_index = title.find('pn-') - 1
            title = title[0:starting_index]

        uid = f'p{format(page_index, "03")}'
        book.add_item(epub.EpubItem(uid=uid,
                                    file_name=xhtml,
                                    media_type='application/xhtml+xml',
                                    content=open(f'{html_file_path}/{xhtml}').read()))

        if any(name in title for name in ('Front and Back Cover', 'Back Cover', 'Installation')):
            insert_last.append((xhtml, page_index))
            page_index += 1
            continue
        elif '_Title_Image_' in xhtml:
            starting_index = title.find(' Title Image ')
            title = title[0:starting_index]
            book.toc.append(epub.Link(xhtml, title, uid))
        elif any(name in xhtml for name in ('_Title_Page', '_Table_of_Contents_', '_Afterword', '_School_Rules')):
            book.toc.append(epub.Link(xhtml, title, uid))
        elif any(name in xhtml for name in ('_Glossary_', '_Character_Introduction_', '_Uniform_',
                                            '_Characters_', '_World_', '_World_Info_', '_History_', '_Introduction_')):
            if title in ('Characters', 'Characters 1'):
                title = 'Characters'
            elif title in ('Character Introduction', 'Character Introduction 1'):
                title = 'Character Introduction'
            elif title in ('Glossary', 'Glossary 1'):
                title = 'Glossary'
            elif title in ('History', 'History 1'):
                title = 'History'
            elif title in ('Uniform', 'Uniform 1'):
                title = 'Uniform'
            elif title in ('Introduction', 'Introduction 1'):
                title = 'Introduction'
            elif title in ('World Info', 'World Info 1'):
                title = 'World Info'
            elif title in ('World', 'World 1'):
                title = 'World'
            else:
                book.spine.append(uid)
                page_index += 1
                continue
            book.toc.append(epub.Link(xhtml, title, uid))
        elif any(name in xhtml for name in ('_Cover_', '_Front_Cover_')):
            continue
        elif not any(name in xhtml for name in ('_Image_', '_Part_', '_Chapter_')):
            book.toc.append(epub.Link(xhtml, f'Illustration {illustration_index}', uid))
            illustration_index += 1
        book.spine.append(uid)
        page_index += 1

    if insert_last:
        for xhtml, l_page_index in insert_last:
            title = xhtml.strip(f'format({l_page_index}, "03")_').strip('.xhtml').replace('_', ' ')

            if 'pn-' in title:
                starting_index = title.find('pn-') - 1
                title = title[0:starting_index]

            uid = f'p{format(l_page_index, "03")}'
            book.toc.append(epub.Link(xhtml, title, uid))
            book.spine.append(uid)
            page_index += 1
