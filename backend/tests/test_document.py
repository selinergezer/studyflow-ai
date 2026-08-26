import unittest
from types import SimpleNamespace

from app.api.document import get_documents


class _DocumentListQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def all(self):
        return self.rows


class _DocumentListDb:
    def __init__(self, rows):
        self.rows = rows
        self.selected_columns = ()

    def query(self, *columns):
        self.selected_columns = columns
        return _DocumentListQuery(self.rows)


class DocumentApiTests(unittest.TestCase):
    def test_get_documents_selects_and_returns_only_list_fields(self):
        db = _DocumentListDb(
            [
                (
                    7,
                    "notes.pdf",
                    "2026-08-25T12:00:00+00:00",
                    3,
                    12,
                )
            ]
        )

        result = get_documents(
            db=db,
            current_user=SimpleNamespace(id=1),
        )

        self.assertEqual(
            [column.key for column in db.selected_columns],
            ["id", "filename", "uploaded_at", "course_id", "page_count"],
        )
        self.assertEqual(
            result,
            [
                {
                    "id": 7,
                    "filename": "notes.pdf",
                    "uploaded_at": "2026-08-25T12:00:00+00:00",
                    "course_id": 3,
                    "page_count": 12,
                }
            ],
        )
        self.assertNotIn("text", result[0])
        self.assertNotIn("file_path", result[0])
        self.assertNotIn("summary", result[0])


if __name__ == "__main__":
    unittest.main()
