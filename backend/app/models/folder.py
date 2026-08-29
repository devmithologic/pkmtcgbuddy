"""Folders for organizing decks.

A tree, and that is why there is a modeling decision worth naming. MongoDB
documents five ways to store a tree —parent reference, child references,
array of ancestors, materialized paths and nested sets— and they are
distinguished by which query they make cheap:

    parent reference       going up is trivial; pulling down an entire
                           subtree needs $graphLookup or several round trips
    array of ancestors     {ancestors: X} gives the subtree in a single
                           indexed query, but moving a folder forces
                           rewriting the array on ALL of its descendants
    materialized paths     just as fast with an anchored regex, same cost
                           on move, and on top of that you must escape the
                           separator

Here we use **parent reference**, the simplest one, and the reason is size:
a user will have five or ten folders. The whole collection fits in one
query and the tree is assembled in memory, so the query that parent
reference makes expensive —walking down the tree— never actually happens
here.

The other four exist for collections where fetching everything is
unthinkable. With ten documents they would be expensive machinery to
maintain in order to speed up something that is already instant.
"""

from pydantic import BaseModel, Field, field_validator


def _clean_name(value: str) -> str:
    """Trims and collapses whitespace. Does not lowercase, unlike tags: a
    folder is a title the user types and wants to see as-is, not a key it
    is grouped by."""
    return " ".join(value.split())


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def normalize(cls, v: str) -> str:
        return _clean_name(v)


class FolderUpdate(BaseModel):
    """Rename or move.

    Watch `parent_id`: here `None` **means something** —"move it to the
    root"— and is not the same as not sending the field. It is exactly the
    opposite of a deck's `name`, where a null can only be a client mistake
    and is dropped.

    The two cases are distinguished with `exclude_unset`, which separates
    "it wasn't sent" from "it was sent as null". Without it there would be
    no way to take a folder out of its parent.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        return _clean_name(v) if v is not None else None


class FolderOut(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    # Decks hanging DIRECTLY off this folder, not counting the ones in its
    # children. The frontend adds up the total with descendants, since it
    # already has the tree assembled: doing it here would force walking it
    # twice.
    deck_count: int = 0
