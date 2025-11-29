import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import argparse
import re

def get_video_url_from_player_page(player_url):
    """
    Scrapes a Granicus player page to find the direct video stream URL.
    This logic is adapted from the proven code in lib/hosts/granicus.py.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36'
        }
        response = requests.get(player_url, headers=headers)
        response.raise_for_status()
        
        m3u8_match = re.search(r'video_url="([^"]+\.m3u8[^"]*)"', response.text)
        video_url = m3u8_match.group(1) if m3u8_match else None

        # Look for MP4 download link
        mp4_match = re.search(r'href="([^"]+\.mp4)"', response.text)
        download_url = mp4_match.group(1) if mp4_match else None

        if not video_url:
             # Fallback for other formats from the proven script
            archive_match = re.search(r'archive_url:\s*\'(.*?)\'', response.text)
            if archive_match:
                video_url = archive_match.group(1)

        if not download_url:
            download_url = video_url

        return {
            'video_url': video_url,
            'download_url': download_url
        }
    except requests.exceptions.RequestException:
        return {'video_url': None, 'download_url': None}


def get_recent_meetings(committee_id=10, start_date_str='2024_01_01', count=1):
    """
    Retrieves a list of the most recent meetings for a given committee, including
    the direct video URL.
    """
    committee_url = f"https://sanfrancisco.granicus.com/ViewPublisher.php?view_id={committee_id}"
    start_date = datetime.strptime(start_date_str, '%Y_%m_%d')
    
    all_meetings = []

    try:
        response = requests.get(committee_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        meeting_table = soup.find('table', id='archive')
        if not meeting_table or not meeting_table.find('tbody'):
            return []

        meeting_rows = meeting_table.find('tbody').find_all('tr')
        
        for row in meeting_rows:
            columns = row.find_all('td')
            if len(columns) < 2:
                continue

            date_str = columns[0].text.strip()
            try:
                if columns[0].find('span'):
                    columns[0].span.decompose()
                    date_str = columns[0].text.strip()
                
                meeting_date = datetime.strptime(date_str, '%m/%d/%y')
            except ValueError:
                try:
                    meeting_date = datetime.strptime(date_str, '%b %d, %Y')
                except ValueError:
                    continue

            if meeting_date >= start_date:
                player_page_url = None
                links = row.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    if 'MediaPlayer.php' in href:
                        player_page_url = f"https:{href}" if href.startswith('//') else href
                        break

                if not player_page_url:
                    continue

                urls = get_video_url_from_player_page(player_page_url)
                direct_video_url = urls.get('video_url')
                download_url = urls.get('download_url')
                
                if not direct_video_url:
                    continue

                meeting_data = {
                    "name": columns[0].get('headers', [''])[0],
                    "date": meeting_date.strftime('%Y-%m-%d'),
                    "duration": columns[1].text.strip().replace('\xa0', ' '),
                    "player_page_url": player_page_url,
                    "video_url": direct_video_url,
                    "download_url": download_url,
                    "agenda_url": None,
                    "minutes_url": None,
                    "transcript_url": None,
                    "mp3_url": None
                }

                for link in links:
                    href = link.get('href', '')
                    full_url = f"https:{href}" if href.startswith('//') else href

                    if 'agendaviewer.php' in href.lower():
                        meeting_data['agenda_url'] = full_url
                    elif 'minutesviewer.php' in href.lower():
                        meeting_data['minutes_url'] = full_url
                    elif 'transcriptviewer.php' in href.lower():
                        meeting_data['transcript_url'] = full_url

                    elif '.mp3' in href:
                        meeting_data['mp3_url'] = href
                    elif '.mp4' in href:
                         # Keep this as a backup if found in row, though player page is preferred
                        meeting_data['download_url'] = href

                if not meeting_data.get('download_url'):
                    meeting_data['download_url'] = meeting_data['video_url']

                all_meetings.append(meeting_data)

        all_meetings.sort(key=lambda x: x['date'], reverse=True)
        return all_meetings[:count]

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Fetch recent meetings from Granicus.")
    parser.add_argument('--committee_id', type=int, default=10, help="The Granicus view_id for the committee.")
    parser.add_argument('--start_date', type=str, default='2025_07_01', help="The start date in YYYY_MM_DD format.")
    parser.add_argument('--count', type=int, default=1, help="The number of recent meetings to return.")
    args = parser.parse_args()

    meetings = get_recent_meetings(args.committee_id, args.start_date, args.count)
    
    if meetings:
        output_file = "temp_meeting_list.json"
        with open(output_file, 'w') as f:
            json.dump(meetings, f, indent=4)
        print(f"Successfully saved {len(meetings)} meeting(s) to {output_file}")
    else:
        print("No meetings found matching the criteria.")
