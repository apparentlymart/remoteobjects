#!/usr/bin/env python

"""

An example Netflix API client, implemented using remoteobjects.

"""

__version__ = '1.0'
__date__ = '25 August 2009'
__author__ = 'Mark Paschal'


import cgi
from optparse import OptionParser
import sys
from urllib import urlencode
import urlparse
from xml.etree import ElementTree

import httplib2
from oauth.oauth import OAuthConsumer, OAuthRequest, OAuthSignatureMethod_HMAC_SHA1

from remoteobjects import RemoteObject, fields, PageObject


class Flixject(RemoteObject):

    content_types = ('text/xml', 'application/xml')
    api_token = None

    def get_request(self, headers=None, **kwargs):
        request = super(Flixject, self).get_request(headers=headers, **kwargs)
        method = request.get('method', 'GET')

        # Apply OAuthness.
        csr = OAuthConsumer(*self.api_token)
        orq = OAuthRequest.from_consumer_and_token(csr, http_method=method,
            http_url=request['uri'])

        # OAuthRequest will strip our query parameters, so add them back in.
        parts = list(urlparse.urlparse(self._location))
        queryargs = cgi.parse_qs(parts[4], keep_blank_values=True)
        for key, value in queryargs.iteritems():
            orq.set_parameter(key, value[0])

        # Sign the request.
        osm = OAuthSignatureMethod_HMAC_SHA1()
        orq.set_parameter('oauth_signature_method', osm.get_name())
        orq.sign_request(osm, csr, None)

        if method == 'GET':
            request['uri'] = orq.to_url()
        else:
            request['headers'].update(orq.to_header())

        return request

    def update_from_tree(self, tree):
        data = dict((k, v(tree)) for k, v in self.decoder_ring.items())
        self.update_from_dict(data)
        return self

    def update_from_response(self, url, response, content):
        self.raise_for_response(url, response, content)

        tree = ElementTree.fromstring(content)
        self.update_from_tree(tree)


class Title(Flixject):

    api_url = fields.Field()
    title   = fields.Field()
    link    = fields.Field()
    thumb   = fields.Field()
    #synopsis = fields.Link(...)

    decoder_ring = {
        'title': lambda x: x.find('title').get('regular'),
        'link':  lambda x: [j for j in x.findall('link') if j.get('rel') == 'alternate'][0].get('href'),
        'thumb': lambda x: x.find('box_art').get('large'),
        'api_url': lambda x: x.find('id'),
    }


class Catalog(Flixject):

    results = fields.List(fields.Field())
    total   = fields.Field()
    offset  = fields.Field()
    limit   = fields.Field()

    decoder_ring = {
        'results': lambda x: [Title().update_from_tree(tree) for tree in x.findall('catalog_title')],
        'total':   lambda x: int(x.find('number_of_results').text),
        'offset':  lambda x: int(x.find('start_index').text),
        'limit':   lambda x: int(x.find('results_per_page').text),
    }


def do_search(opts, args):
    query = ' '.join(args)

    search = Catalog.get('http://api.netflix.com/catalog/titles').filter(term=query)
    search.deliver()

    if len(search.results) == 0:
        print "No results for %r" % query
    elif len(search.results) == 1:
        result = search.results[0]
        print "## %s ##" % result.title
    else:
        print "## Results for %r ##" % query
        print
        for title in search.results:
            if title is None:
                print "(oops, none)"
            else:
                print title.title

    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv

    parser = OptionParser()
    parser.add_option("-k", "--key", dest="key",
        help="Netflix API key (required)")
    parser.add_option("-s", "--secret", dest="secret",
        help="Netflix API shared secret (required)")
    parser.add_option("--search", action="store_const", const=do_search,
        dest="action", default=do_search,
        help="Search for an item by title (default)")
    opts, args = parser.parse_args()

    if opts.key is None or opts.secret is None:
        print >>sys.stderr, "Options --key and --secret are required"
        return 1

    Flixject.api_token = (opts.key, opts.secret)

    return opts.action(opts, args)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
