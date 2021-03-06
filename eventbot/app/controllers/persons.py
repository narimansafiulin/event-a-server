"""
Event Bot Server
"""

import asyncpgsa
from asyncpg.connection import Connection
from asyncpg.exceptions import PostgresError
from sanic import response
from sanic.views import HTTPMethodView
from sqlalchemy.sql import select

from eventbot.app import models
from eventbot.app import helpers
from eventbot.lib import exceptions
from eventbot.lib import response_wrapper


class PersonsController(HTTPMethodView):

    @helpers.db_connections.provide_connection()
    async def get(self, request, event_id, connection):
        """Returns a list of event persons."""

        # Check, is event exists
        try:
            query_event = (select([models.event.t])
                .select_from(models.event.t)
                .where(models.event.t.c.id == event_id)
                .apply_labels())
            query_event, params = asyncpgsa.compile_query(query_event)

            try:
                row = await connection.fetchrow(query_event, *params)
            except PostgresError:
                raise exceptions.NotFetchedError

            if not row:
                raise exceptions.NotFoundError

            event = models.event.t.parse(row, prefix="events_")
        except exceptions.NotFoundError:
            return response.json(
                response_wrapper.error("Event not found"),
                status=404)

        # If event exists, query all persons
        query = (select([models.person.t])
            .select_from(models.person.t)
            .where(models.person.t.c.event_id == event["id"])
            .order_by(models.person.t.c.name.asc())
            .order_by(models.person.t.c.id.desc())
            .apply_labels())

        # Compile query, execute and parse
        query, params = asyncpgsa.compile_query(query)
        try:
            rows = await connection.fetch(query, *params)
        except PostgresError:
            raise exceptions.NotFetchedError

        persons = [
            models.person.json_format(models.person.t.parse(row, prefix="persons_"))
            for row in rows
        ]

        # Return the list
        return response.json(response_wrapper.ok(persons))

    @helpers.db_connections.provide_connection()
    async def post(self, request, event_id, connection):
        """Creates a new event person."""

        # Person form
        person = request.json

        # Check, is event exists
        try:
            query_event = (select([models.event.t])
                .select_from(models.event.t)
                .where(models.event.t.c.id == event_id)
                .apply_labels())
            query_event, params = asyncpgsa.compile_query(query_event)

            try:
                row = await connection.fetchrow(query_event, *params)
            except PostgresError:
                raise exceptions.NotFetchedError

            if not row:
                raise exceptions.NotFoundError

            event = models.event.t.parse(row, prefix="events_")
        except exceptions.NotFoundError:
            return response.json(
                response_wrapper.error("Event not found"),
                status=404)

        # If event exists, create a transaction
        # We need to 1) save person, 2) fetch person from a database
        async with connection.transaction():
            try:
                query = (models.person.t
                    .insert()
                    .values(event_id=event["id"],
                            name=person["name"])
                    .returning(models.person.t.c.id))
                query, params = asyncpgsa.compile_query(query)

                id = await connection.fetchval(query, *params)

                query = (select([models.person.t])
                    .select_from(models.person.t)
                    .where(models.person.t.c.id == id)
                    .apply_labels())
                query, params = asyncpgsa.compile_query(query)

                try:
                    row = await connection.fetchrow(query, *params)
                except PostgresError:
                    raise exceptions.NotFetchedError

                if not row:
                    raise exceptions.NotFoundError

                person = models.person.json_format(
                    models.person.t.parse(row, prefix="persons_"))
            except (PostgresError, exceptions.DatabaseError):
                raise exceptions.NotCreatedError

        return response.json(response_wrapper.ok(person), status=201)
