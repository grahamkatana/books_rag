from marshmallow import Schema, fields


class LoginRequestSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class LoginResponseSchema(Schema):
    access_token = fields.Str()
    email = fields.Str()
    is_admin = fields.Bool()


class MeResponseSchema(Schema):
    id = fields.Int()
    email = fields.Str()
    is_admin = fields.Bool()
