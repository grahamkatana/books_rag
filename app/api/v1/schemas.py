from marshmallow import Schema, fields
from marshmallow.validate import OneOf

from app.config import DEFAULT_TOP_K, DEFAULT_CHAT_MODEL


class AskRequestSchema(Schema):
    question = fields.Str(required=True, metadata={"description": "The question to ask the library"})
    chat_id = fields.Int(required=False, allow_none=True,
                          metadata={"description": "Continue an existing chat instead of starting a new one"})
    sources = fields.List(fields.Str(), required=False, load_default=None,
                          metadata={"description": "Restrict search to one or more books' source_key, overriding edition preference"})
    top_k = fields.Int(required=False, load_default=DEFAULT_TOP_K)
    model = fields.Str(required=False, load_default=DEFAULT_CHAT_MODEL)
    all_editions = fields.Bool(required=False, load_default=False,
                                metadata={"description": "Search every edition of a book instead of just the preferred one"})
    corpus = fields.Str(required=False, load_default="books", validate=OneOf(["books", "papers", "both"]),
                         metadata={"description": "Which library to search: 'books' (default), 'papers', or 'both'"})


class CitationSchema(Schema):
    apa_text = fields.Str()
    locator = fields.Str(allow_none=True)
    book_id = fields.Int(allow_none=True)
    paper_id = fields.Int(allow_none=True)


class AskResponseSchema(Schema):
    chat_id = fields.Int()
    answer = fields.Str()
    citations = fields.List(fields.Nested(CitationSchema))


class BookSchema(Schema):
    id = fields.Int()
    source_key = fields.Str()
    title = fields.Str()
    authors = fields.Str(allow_none=True)
    is_editor = fields.Bool()
    year = fields.Int(allow_none=True)
    publisher = fields.Str(allow_none=True)
    edition = fields.Str(allow_none=True)
    page_mode = fields.Str()
    work_key = fields.Str(allow_none=True)
    is_preferred_edition = fields.Bool()
    bibliography_verified = fields.Bool()


class MessageSchema(Schema):
    id = fields.Int()
    role = fields.Str()
    content = fields.Str()
    created_at = fields.DateTime()
    citations = fields.List(fields.Nested(CitationSchema))


class ChatSummarySchema(Schema):
    id = fields.Int()
    title = fields.Str(allow_none=True)
    created_at = fields.DateTime()
    message_count = fields.Int()


class ChatDetailSchema(Schema):
    id = fields.Int()
    title = fields.Str(allow_none=True)
    created_at = fields.DateTime()
    messages = fields.List(fields.Nested(MessageSchema))