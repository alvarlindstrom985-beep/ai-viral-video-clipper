import unittest

from app.main import parse_youtube_rss


class YouTubeSourceDiscoveryTests(unittest.TestCase):
    def test_parses_public_video_metadata_without_media_download(self):
        feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <entry>
            <id>yt:video:abcdefghijk</id>
            <yt:videoId>abcdefghijk</yt:videoId>
            <yt:channelId>UC1234567890123456789012</yt:channelId>
            <title>Streamer reacts to GTA chaos</title>
            <published>2026-11-10T08:00:00+00:00</published>
            <link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/>
          </entry>
        </feed>"""
        result = parse_youtube_rss(feed)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["video_id"], "abcdefghijk")
        self.assertEqual(result[0]["title"], "Streamer reacts to GTA chaos")
        self.assertEqual(result[0]["url"], "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(result[0]["source"], "YouTube RSS")

    def test_skips_invalid_or_incomplete_entries(self):
        feed = """<feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <entry><yt:videoId>short</yt:videoId><title>Bad ID</title></entry>
          <entry><yt:videoId>abcdefghijk</yt:videoId><title> </title></entry>
        </feed>"""
        self.assertEqual(parse_youtube_rss(feed), [])

    def test_rejects_malformed_xml(self):
        with self.assertRaises(ValueError):
            parse_youtube_rss("<feed>")


if __name__ == "__main__":
    unittest.main()
