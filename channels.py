#
# Parse all multicast URL's from the IPTV stream list
# (Python 3!)
#
import argparse
import json
import collections
import re
import urllib

import requests

import pprint

# Channel = collections.namedtuple('Channel', ['name', 'url', 'extras'])
Channel = collections.namedtuple('Channel', ['name', 'url', 'logo', 'extras'])


class ParseVLC(object):

    # line_regex = re.compile("#EXT(?P<tag>\\w+):(?P<value>-?\\d+) (?P<param>.*)")
    # line_regex = re.compile("#EXT(?P<tag>\\w+):(?P<value>-?\\d+) +tvg-ID=\"(?P<tvg_ID>[^\"]*)\" +(?P<param>.*)")
    # line_regex = re.compile("#EXT(?P<tag>\\w+):(?P<value>-?\\d+) +tvg-ID=\"(?P<tvg_ID>[^\"]*)\" +tvg-name=\"(?P<tvg_name>[^\"]*)\" +(?P<param>.*)")
    line_regex = re.compile("#EXT(?P<tag>\\w+):(?P<value>-?\\d+) +tvg-ID=\"(?P<tvg_ID>[^\"]*)\" +tvg-name=\"(?P<tvg_name>[^\"]*)\" +tvg-logo=\"(?P<tvg_logo>[^\"]*)\" +group-title=\"(?P<group_title>[^\"]*)\" *, *(?P<name>[^,]+)")

    def __init__(self, file_handle):
        self.file = file_handle

    def __iter__(self):
        ext_m3u = False

        buffer = []

        # all lines, with whitespace stripped, and blank lines filtered
        for line in filter(bool, [line.strip() for line in self.file]):
            # eat everything until a non-header line was found
            if not ext_m3u:
                if 'EXTM3U' in line:
                    ext_m3u = True
                continue

            buffer.append(line)

            # is it not a option? -> it is the address
            if not self.line_regex.match(line):
                yield self.parse_section(buffer)
                buffer = []

    def parse_section(self, section):
        name = None
        url = None
        logo = None
        extras = {}

        for line in section:
            m = self.line_regex.match(line)
            if m:
                tag, value, tvg_id, tvg_name, tvg_logo, group_title, name = m.groups()
                if tag == 'INF':
                    # print('Value:', value)
                    # print('tvg-ID:', tvg_id)
                    # print('tvg-name:', tvg_name)
                    # print('tvg-logo:', tvg_logo)
                    # print('group-title:', group_title)
                    # print('name:', name)
                    logo = tvg_logo
                    extras['tvg-ID'] = tvg_id
                    extras['tvg-name'] = tvg_name
                    extras['group-title'] = group_title
                if tag == 'VLCOPT':
                    key, val = value.split('=')
                    extras[key] = val
            else:
                url = line

        return Channel(name, url, logo, extras)


"""
Wrapper for a Tvheadend instance
"""


class TvheadendAPI(object):
    def __init__(self, root, user=None, pw=None, interface='eth0'):
        self.root_url = root
        self.interface = interface
        self.auth = (user, pw) if user else None

    def post(self, sub_url, data):
        url = urllib.parse.urljoin(self.root_url, sub_url)

        res = requests.post(url,  data=data, auth=self.auth)
        return res.json()

    def get(self, sub_url, params):
        url = urllib.parse.urljoin(self.root_url, sub_url)

        res = requests.get(url,  params=params, auth=self.auth)
        return res.json()

    """
    Add IPTV channel to the first Tvheadend mux
    with the first index. Make sure that max input streams
    attribute of the Network is set low enough (!)

    channel: Channel namedtuple for given channel
    """
    def add_mux(self, channel):
        # Get the UUID of the iptv network by assuming it is the first
        uuid_request = self.post("/api/idnode/load", data={
            'class': "mpegts_network",
            'enum': 1,
            'query': ''
        })

        if not uuid_request['entries']:
            print("""Make sure that there exists a network in tvheadend.

            It should be of IPTV type and the number of maximum input
            streams should be low.

            Tvheadend will try to subscribe to all the channels that get
            added. If this number is too high, it could cause your tvheadend
            instance to stop responding.
            """)

        network_uuid = uuid_request['entries'][0]['key']

        # Copié de ... https://github.com/edit4ever/script.module.tvh2kodi/blob/master/default.py
        #     mux_create_url = 'http://' + tvh_url + ':' + tvh_port + '/api/mpegts/network/mux_create?conf={"enabled":1,"epg":1,"iptv_url":"' + sel_url + '","iptv_atsc":' + str(sel_atsc) + ',"iptv_muxname":"' + str(sel_name) + '","channel_number":"' + str(sel_chnum) + '","iptv_sname":"' + str(sel_service) + '","scan_state":0,"charset":"","priority":0,"spriority":0,"iptv_substitute":false,"iptv_interface":"","iptv_epgid":"","iptv_icon":"","iptv_tags":"","iptv_satip_dvbt_freq":0,"iptv_buffer_limit":0,"tsid_zero":false,"pmt_06_ac3":0,"eit_tsid_nocheck":false,"sid_filter":0,"iptv_respawn":false,"iptv_kill":0,"iptv_kill_timeout":5,"iptv_env":"","iptv_hdr":""}&uuid=' + str(net_uuid_sel)
        self.post("/api/mpegts/network/mux_create", data={
            'uuid': network_uuid,
            'conf': json.dumps({
                "enabled": 1,
                "skipinitscan": 1,
                "iptv_muxname": channel.name,
                "iptv_sname": channel.name,
                "iptv_url": channel.url,
                "iptv_interface": self.interface,
                "iptv_icon": channel.logo,
                "charset": "AUTO"
            })
        })

    def add_mux_test(self, channel):
        "Simulation add_mux"
        network_uuid = 'unknown in test mode'
        data = {
            'uuid': network_uuid,
            'conf': json.dumps({
                "enabled": 1,
                "skipinitscan": 1,
                "iptv_muxname": channel.name,
                "iptv_sname": channel.name,
                "iptv_url": channel.url,
                "iptv_interface": self.interface,
                "iptv_icon": channel.logo,
                "charset": "AUTO"
            })
        }
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(data)
        print('extras: ')
        pp.pprint(channel.extras)

    def list_muxes(self):
        res = self.post("/api/mpegts/mux/grid", data={
            'start': 0,
            'limit': 999999999,
            'sort': 'name',
            'dir': 'ASC',
        })
        for mux in res['entries']:
            yield Channel(mux['name'], mux['iptv_url'], mux)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Bulk-add channels to Tvheadend, from a M3U file')
    parser.add_argument('m3u_file', type=argparse.FileType('r'))
    parser.add_argument('tvheadend_url',
                        help='URL to tvheadend, e.g. http://192.168.1.2:9981')
    parser.add_argument('--user', default=None, help="username")
    parser.add_argument('--password', default=None, help="password")
    parser.add_argument('--interface', default='eth0',
                        help='interface name TVHeadend tunes on (e.g. eth0)')

    args = parser.parse_args()

    m3u_parser = ParseVLC(args.m3u_file)
    tvh = TvheadendAPI(args.tvheadend_url, args.user, args.password,
                       args.interface)

    # Create a dict of the URL's of known channels:
    # known_channels = {m.url: m for m in tvh.list_muxes()}
    known_channels = {}

    for channel in m3u_parser:
        print('Adding muxes to TvheadendAPI...')
        if channel.url not in known_channels:
            tvh.add_mux(channel)
            print('added: {} at {}'.format(channel.name, channel.url))
        else:
            print('skipped: {} at {}'.format(channel.name, channel.url))
