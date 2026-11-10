import tempfile
import unittest
from pathlib import Path
from pipeline.core import sha256


class DateGuardTests(unittest.TestCase):
    def test_original_date_and_event_must_both_be_yesterday_with_readable_proof(self):
        from pipeline.date_guard import validate_date_proof
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.txt';p.write_text('2026-11-08 12:05 announced today',encoding='utf8')
            proof=dict(kind='original_publication',source_url='https://example.org/a',
                       published_at='2026-11-08T12:05:00+08:00',date_text='2026-11-08 12:05',
                       path=str(p),sha256=sha256(p),event_date='2026-11-08',
                       event_date_note='Original announcement dated November 8.',source_timezone='Asia/Shanghai')
            story=dict(id='one',source_url=proof['source_url'],published_at=proof['published_at'],date_evidence=proof)
            edition=dict(date='2026-11-09',stories=[story])
            validate_date_proof(edition)
            for changes in [dict(kind='reprint'),dict(kind='hn_submission'),
                            dict(published_at='2026-11-06T12:05:00+08:00'),
                            dict(event_date='2026-11-07'),dict(date_text='not in original'),
                            dict(sha256='0'*64)]:
                with self.subTest(changes=changes),self.assertRaises(ValueError):
                    validate_date_proof(dict(edition,stories=[dict(story,date_evidence=dict(proof,**changes))]))

            # UTC calendar dates differ from the actual Shanghai publication day.
            for stamp, allowed in [('2026-11-07T15:59:59+00:00',False),
                                   ('2026-11-07T16:00:00+00:00',True),
                                   ('2026-11-08T15:59:59+00:00',True),
                                   ('2026-11-08T16:00:00+00:00',False)]:
                variant=dict(story,published_at=stamp,date_evidence=dict(proof,published_at=stamp))
                with self.subTest(stamp=stamp):
                    if allowed: validate_date_proof(dict(edition,stories=[variant]))
                    else:
                        with self.assertRaises(ValueError):validate_date_proof(dict(edition,stories=[variant]))
            day_only=dict(story,time_precision='day',date_evidence=dict(proof,source_timezone='America/Los_Angeles'))
            with self.assertRaises(ValueError):validate_date_proof(dict(edition,stories=[day_only]))

    def test_discovery_time_cannot_be_used_as_verified_original_time(self):
        from pipeline.collect import candidate_date_metadata
        hn=candidate_date_metadata('hn','2026-11-08T09:00:00+08:00')
        self.assertEqual(hn['date_basis'],'submission_time')
        self.assertIsNone(hn['original_published_at'])
        self.assertEqual(hn['original_date_status'],'unverified')

    def test_current_daily_run_rejects_wrong_issue_date_but_explicit_archive_is_allowed(self):
        from pipeline.date_guard import validate_issue_day
        from datetime import date
        with self.assertRaises(ValueError):validate_issue_day('2026-11-08',date(2026,11,9))
        validate_issue_day('2026-11-08',date(2026,11,9),archive=True)
        with self.assertRaises(ValueError):validate_issue_day('2026-11-09',date(2026,11,9),archive=True)
        with self.assertRaises(ValueError):validate_issue_day('2026-11-10',date(2026,11,9),archive=True)


if __name__=='__main__':unittest.main()
