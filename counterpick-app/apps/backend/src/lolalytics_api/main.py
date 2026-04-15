import json
import requests
from lxml import html
from lolalytics_api.errors import InvalidLane, InvalidRank


def display_ranks(display: bool = True) -> dict:
    """
    Display all available ranks and their shortcuts.
    :param display: If True (default), prints the ranks to the console. Otherwise, returns a dict.
    :return: None or dict of ranks if display is False.
    """
    rank_mappings = {
            '': '',
            'challenger': 'challenger',
            'chall': 'challenger',
            'c': 'challenger',
            'grandmaster_plus': 'grandmaster_plus',
            'grandmaster+': 'grandmaster_plus',
            'gm+': 'grandmaster_plus',
            'grandmaster': 'grandmaster',
            'grandm': 'grandmaster',
            'gm': 'grandmaster',
            'master_plus': 'master_plus',
            'master+': 'master_plus',
            'mast+': 'master_plus',
            'm+': 'master_plus',
            'master': 'master',
            'mast': 'master',
            'm': 'master',
            'diamond_plus': 'diamond_plus',
            'diamond+': 'diamond_plus',
            'diam+': 'diamond_plus',
            'dia+': 'diamond_plus',
            'd+': 'diamond_plus',
            'diamond': 'diamond',
            'diam': 'diamond',
            'dia': 'diamond',
            'd': 'diamond',
            'emerald': 'emerald',
            'eme': 'emerald',
            'em': 'emerald',
            'e': 'emerald',
            'platinum+': 'platinum_plus',
            'plat+': 'platinum_plus',
            'pl+': 'platinum_plus',
            'p+': 'platinum_plus',
            'platinum': 'platinum',
            'plat': 'platinum',
            'pl': 'platinum',
            'p': 'platinum',
            'gold_plus': 'gold_plus',
            'gold+': 'gold_plus',
            'g+': 'gold_plus',
            'gold': 'gold',
            'g': 'gold',
            'silver': 'silver',
            'silv': 'silver',
            's': 'silver',
            'bronze': 'bronze',
            'br': 'bronze',
            'b': 'bronze',
            'iron': 'iron',
            'i': 'iron',
            'unranked': 'unranked',
            'unrank': 'unranked',
            'unr': 'unranked',
            'un': 'unranked',
            'none': 'unranked',
            'null': 'unranked',
            '-': 'unranked',
            'all': 'all',
            'otp': '1trick',
            '1trick': '1trick',
            '1-trick': '1trick',
            '1trickpony': '1trick',
            'onetrickpony': '1trick',
            'onetrick': '1trick',
        }
    if display:
        print("Available ranks and their shortcuts:")
        for rank, shortcut in rank_mappings.items():
            print(f"{rank}: {shortcut}")
    else:
        return rank_mappings


def display_lanes(display: bool = True) -> dict:
    """
    Display all available lanes and their shortcuts.
    :param display: If True (default), prints the lanes to the console. Otherwise, returns a dict.
    :return: None or dict of lanes if display is False.
    """
    lane_mappings = {
        '': '',
        'top': 'top',
        'jg': 'jungle',
        'jng': 'jungle',
        'jungle': 'jungle',
        'mid': 'middle',
        'middle': 'middle',
        'bottom': 'bottom',
        'bot': 'bottom',
        'adc': 'bottom',
        'support': 'support',
        'supp': 'support',
        'sup': 'support'
    }
    if display:
        print("Available lanes and their shortcuts:")
        for lane, shortcut in lane_mappings.items():
            print(f"{lane}: {shortcut}")
    else:
        return lane_mappings


def _sort_by_rank(link: str, rank: str) -> str:
    """
    Update the link to sort by a specific rank.
    :param link: url to the page to sort.
    :param rank: sort by rank (see ``display_ranks()``).
    :return: new link with the rank filter applied.
    """
    rank_mappings = display_ranks(display=False)
    try:
        mapped_rank = rank_mappings[rank.lower()]
    except KeyError:
        raise InvalidRank(rank)

    if '?' in link:
        return f'{link}&tier={mapped_rank}'
    else:
        return f'{link}?tier={mapped_rank}'


def _sort_by_lane(link: str, lane: str) -> str:
    """
    Update the link to filter by a specific lane.
    :param link: url to the page to filter.
    :param lane: lane to filter by (see ``display_lanes()``).
    :return: new link with the lane filter applied.
    """
    lane_mappings = display_lanes(display=False)
    try:
        mapped_lane = lane_mappings[lane.lower()]
    except KeyError:
        raise InvalidLane(lane)

    if '?' in link:
        return f'{link}&lane={mapped_lane}'
    else:
        return f'{link}?lane={mapped_lane}'


def _set_patch(link: str, patch: str) -> str:
    """
    Update the link to filter by a specific patch version.
    :param link: url to the page to filter.
    :param patch: patch version (e.g. '15.23', '15.22').
    :return: new link with the patch filter applied.
    """
    if not patch:
        return link
    
    if '?' in link:
        return f'{link}&patch={patch}'
    else:
        return f'{link}?patch={patch}'


def get_tierlist(n: int = 10, lane: str = '', rank: str = '', patch: str = ''):
    """
    Get the top n champions in the tier list for a specific lane.
    :param n: number of champions to return.
    :param lane: lane to filter the tier list by (see ``display_lanes()``).
    :param rank: sort by rank (see ``display_ranks()``).
    :param patch: patch version to filter by (e.g. '15.23', '15.22').
    :return: JSON containing rank, champion name, tier and winrate.
    """
    base_url = 'https://lolalytics.com/lol/tierlist/'

    if lane:
        base_url = _sort_by_lane(base_url, lane)

    if rank:
        base_url = _sort_by_rank(base_url, rank)
    
    if patch:
        base_url = _set_patch(base_url, patch)

    # User-Agent Header hinzufügen (403 Forbidden Fix)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    tierlist_html = requests.get(base_url, headers=headers)
    tree = html.fromstring(tierlist_html.content)
    result = {}

    for i in range(3, n + 3):
        rank_xpath = f'/html/body/main/div[6]/div[{i}]/div[1]'
        champion_xpath = f'/html/body/main/div[6]/div[{i}]/div[3]/a'
        tier_xpath = f'/html/body/main/div[6]/div[{i}]/div[4]'
        winrate_xpath = f'/html/body/main/div[6]/div[{i}]/div[6]/div/span[1]'

        rank = tree.xpath(rank_xpath)[0].text_content().strip()
        champion = tree.xpath(champion_xpath)[0].text_content().strip()
        tier = tree.xpath(tier_xpath)[0].text_content().strip()
        winrate = tree.xpath(winrate_xpath)[0].text_content().strip()

        result[i - 3] = {
            'rank': rank,
            'champion': champion,
            'tier': tier,
            'winrate': winrate
        }

    return json.dumps(result, indent=4)


def get_counters(n: int = 10, champion: str = '', rank: str = '', patch: str = ''):
    """
    Get the top n counters for a specific champion.
    :param n: number of counters to return.
    :param champion: champion to filter the counters by.
    :param rank: sort by rank (see ``display_ranks()``).
    :param patch: patch version to filter by (e.g. '15.23', '15.22').
    :return: JSON containing counter champion name and winrate (vs the counter).
    """
    if champion == '':
        raise ValueError("Champion name cannot be empty")

    counters = f'https://lolalytics.com/lol/{champion}/counters/'
    if rank:
        counters = _sort_by_rank(counters, rank)
    
    if patch:
        counters = _set_patch(counters, patch)

    # User-Agent Header hinzufügen (403 Forbidden Fix)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    counters_html = requests.get(counters, headers=headers)
    tree = html.fromstring(counters_html.content)
    result = {}

    for i in range(1, n + 1):
        champion_xpath = f'/html/body/main/div[6]/div[1]/div[2]/span[{i}]/div[1]/a/div/div[1]'
        winrate_xpath = f'/html/body/main/div[6]/div[1]/div[2]/span[{i}]/div[1]/a/div/div[2]/div'

        try:
            champion_name = tree.xpath(champion_xpath)[0].text_content().strip()
            winrate = tree.xpath(winrate_xpath)[0].text_content().strip()

            result[i - 1] = {
                'champion': champion_name,
                'winrate': winrate.split('%')[0]
            }
        except IndexError:
            # Keine weiteren Counter verfügbar
            break

    return json.dumps(result, indent=4)


def get_synergies(n: int = 10, champion: str = '', rank: str = '', patch: str = ''):
    """
    Get the top n synergies (best teammates) for a specific champion.
    :param n: number of synergies to return.
    :param champion: champion to filter the synergies by.
    :param rank: sort by rank (see ``display_ranks()``).
    :param patch: patch version to filter by (e.g. '15.23', '15.22').
    :return: JSON containing synergy champion name and winrate (with the synergy).
    """
    if champion == '':
        raise ValueError("Champion name cannot be empty")

    # Synergy data is on the build page, similar structure to counters
    # but in a different section (typically div[2] instead of div[1])
    synergies_url = f'https://lolalytics.com/lol/{champion}/build/'
    if rank:
        synergies_url = _sort_by_rank(synergies_url, rank)
    
    if patch:
        synergies_url = _set_patch(synergies_url, patch)

    synergies_html = requests.get(synergies_url)
    tree = html.fromstring(synergies_html.content)
    result = {}

    # Synergy data is typically in div[6]/div[2] (second tab after counters)
    # Try multiple div indices to find the synergy section
    for div_index in [2, 3, 4]:
        success = False
        for i in range(1, n + 1):
            # Try the synergy section XPath
            champion_xpath = f'/html/body/main/div[6]/div[{div_index}]/div[2]/span[{i}]/div[1]/a/div/div[1]'
            winrate_xpath = f'/html/body/main/div[6]/div[{div_index}]/div[2]/span[{i}]/div[1]/a/div/div[2]/div'

            try:
                champion_name = tree.xpath(champion_xpath)[0].text_content().strip()
                winrate = tree.xpath(winrate_xpath)[0].text_content().strip()

                result[i - 1] = {
                    'champion': champion_name,
                    'winrate': winrate.split('%')[0]
                }
                success = True
            except IndexError:
                # No more synergies available in this section
                break
        
        # If we found synergies, break out of div_index loop
        if success and len(result) > 0:
            break

    return json.dumps(result, indent=4)


def get_champion_data(champion: str, lane: str = '', rank: str = '', patch: str = ''):
    """
    Get detailed info about a certain champion.
    :param champion: Champion name to search for.
    :param lane: Lane to filter by (see ``display_lanes()``).
    :param rank: Sort by rank (see ``display_ranks()``).
    :param patch: Patch version to filter by (e.g. '15.23', '15.22').
    :return: JSON containing the data.
    """
    if champion == '':
        raise ValueError("Champion name cannot be empty")

    base_link = f'https://lolalytics.com/lol/{champion}/build/'

    if lane:
        base_link = _sort_by_lane(base_link, lane)

    if rank:
        base_link = _sort_by_rank(base_link, rank)
    
    if patch:
        base_link = _set_patch(base_link, patch)

    # User-Agent Header hinzufügen (403 Forbidden Fix)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    tree = html.fromstring(requests.get(base_link, headers=headers).content)
    result = {}

    labels = [
        'winrate',
        'wr_delta',
        'game_avg_wr',
        'pickrate',
        'tier',
        'rank',
        'banrate',
        'games'
    ]
    for i in range(1, 9):
        """
        This range goes like this:
        For rows: (i // 5) + 1 -> it gives numbers 1, 1, 1, 1, 2, 2, 2, 2
        For columns: ((i - 1) % 4) + 1 -> it gives numbers 1, 2, 3, 4, 1, 2, 3, 4
        So we get the following structure: row 1 has columns 1-4, row 2 has columns 1-4, etc.
        """
        current_xpath = f'/html/body/main/div[5]/div[1]/div[2]/div[2]/div[{(i//5)+1}]/div[{((i-1)%4)+1}]/div[1]'
        result[labels[i-1]] = tree.xpath(current_xpath)[0].text_content().strip().split('\n')[0]

    return json.dumps(result, indent=4)


def matchup(champion1: str, champion2: str, lane: str = '', rank: str = '', patch: str = ''):
    """
    Get the matchup data between two champions.
    :param champion1: First champion name.
    :param champion2: Second champion name.
    :param lane: Lane to filter the matchup by (see ``display_lanes()``).
    :param rank: Sort by rank (see ``display_ranks()``).
    :param patch: Patch version to filter by (e.g. '15.23', '15.22').
    :return: JSON containing matchup data.
    """
    if champion1 == '' or champion2 == '':
        raise ValueError("Champion names cannot be empty")

    base_link = f"https://lolalytics.com/lol/{champion1}/vs/{champion2}/build/"

    if lane:
        base_link = _sort_by_lane(base_link, lane)

    if rank:
        base_link = _sort_by_rank(base_link, rank)
    
    if patch:
        base_link = _set_patch(base_link, patch)

    # User-Agent Header hinzufügen (403 Forbidden Fix)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    tree = html.fromstring(requests.get(base_link, headers=headers).content)

    winrate_xpath = f'/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]'
    nof_games_xpath = f'/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]'

    winrate = tree.xpath(winrate_xpath)[0].text_content().strip()
    nof_games = tree.xpath(nof_games_xpath)[0].text_content().strip()

    result = {
        'winrate': winrate.split('%')[0],
        'number_of_games': nof_games
    }

    return json.dumps(result, indent=4)


def patch_notes(category: str, rank: str = ''):
    """
    Get the latest changes in pick/ban rates.
    :param category: buffed, nerfed, adjusted or all.
    :param rank: Rank to filter the patch notes by (see ``display_ranks()``).
    :return: JSON containing patch notes data.
    """
    base_link = 'https://lolalytics.com/'

    if rank:
        base_link = _sort_by_rank(base_link, rank)

    tree = html.fromstring(requests.get(base_link).content)
    if category == 'all':
        result = {
            'buffed': {},
            'nerfed': {},
            'adjusted': {}
        }
    else:
        result = {
            category: {}
        }

    def _parse_data(_category: str = category):
        category_mapping = {
            'buffed': 1,
            'nerfed': 2,
            'adjusted': 3
        }
        category_idx = category_mapping[_category]

        i = 0
        while True:
            i += 1
            champion_name_xpath = f'/html/body/main/div[5]/div[4]/div[{category_idx}]/div/div[{i}]/div/div[1]/span[1]/a'
            winrate_xpath = f'/html/body/main/div[5]/div[4]/div[{category_idx}]/div/div[{i}]/div/div[2]/span'
            pickrate_xpath = f'/html/body/main/div[5]/div[4]/div[{category_idx}]/div/div[{i}]/div/div[3]/span[1]'
            banrate_xpath = f'/html/body/main/div[5]/div[4]/div[{category_idx}]/div/div[{i}]/div/div[3]/span[2]'

            try:
                result[_category][i - 1] = {
                    'champion': tree.xpath(champion_name_xpath)[0].text_content().strip(),
                    'winrate': tree.xpath(winrate_xpath)[0].text_content().strip(),
                    'pickrate': tree.xpath(pickrate_xpath)[0].text_content().strip(),
                    'banrate': tree.xpath(banrate_xpath)[0].text_content().strip()
                }
            except IndexError:
                break

    if category == 'all':
        _parse_data('buffed')
        _parse_data('nerfed')
        _parse_data('adjusted')
    else:
        _parse_data()

    return json.dumps(result, indent=4)
