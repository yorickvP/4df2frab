from __future__ import annotations

import argparse
import re
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel

from api import AllAPI, LocationAPI, ProgramAPI, api_result, load_api

ROLLOVER_HOUR = 7

MY_NAMESPACE = uuid.UUID("ca6c8e77-59a4-4e51-919c-25e38457f0ee")


def generate_deterministic_uuid(*args):
    # Convert all arguments to strings and join them
    name = ":".join(map(str, args))

    # Generate a UUID using uuid5
    return uuid.uuid5(MY_NAMESPACE, name)


def filter_interesting(program: ProgramAPI) -> bool:
    if program.location is None:
        return False
    loc = program.location.get().top_location
    return loc.slug in ("valkhof-festival", "de-kaaij")


def render_location_name(location: LocationAPI) -> str:
    return (
        location.title.replace("Festival ", "")
        .replace("Stadseiland ", "")
        .replace(" aan de ", "@")
        .replace(" at the ", "@")
        .replace("Park Kronenburg", "Kronenburg")
        .replace(": Hosted by Open Source Radio", "")
    )


def event2frab(event: ProgramAPI) -> ET.Element:
    start = datetime.combine(
        event.day.date.date(), datetime.strptime(event.start_time, "%H:%M").time()
    )
    end = datetime.combine(
        event.day.date.date(), datetime.strptime(event.end_time, "%H:%M").time()
    )
    if start.hour < ROLLOVER_HOUR:
        start += timedelta(days=1)
    if end.hour < ROLLOVER_HOUR:
        end += timedelta(days=1)
    if start >= end:
        print(f"Warning: Event {event.title} starts at {start} and ends at {end}")
        end = start + timedelta(hours=1)
    room = event.location.get().slug if event.location else "none"
    title = event.title
    ret = ET.Element("event")
    ret.set("id", str(event.id))
    ret.set("guid", str(generate_deterministic_uuid(start, room, title)))
    ET.SubElement(ret, "date").text = start.strftime("%Y-%m-%dT%H:%M:00+02:00")
    ET.SubElement(ret, "start").text = start.strftime("%H:%M")
    duration_minutes = (end - start).seconds // 60
    duration_hours = duration_minutes // 60
    ET.SubElement(
        ret, "duration"
    ).text = f"{duration_hours:02}:{duration_minutes % 60:02}"
    ET.SubElement(ret, "room").text = room
    ET.SubElement(ret, "title").text = title
    ET.SubElement(ret, "description").text = event.description
    ET.SubElement(ret, "abstract").text = event.description_short
    ET.SubElement(ret, "type").text = "performance"
    if event.location:
        top_location = event.location.get().top_location
        ET.SubElement(ret, "track").text = render_location_name(top_location)
    ET.SubElement(ret, "language")  # .text = "en"
    slug = event.slug.encode("ascii", "ignore").decode()
    ET.SubElement(ret, "slug").text = f"vierdaagsef-2024-{event.id!s}-{slug}"
    ET.SubElement(ret, "subtitle")  # xs:string
    xrec = ET.SubElement(ret, "recording")
    ET.SubElement(xrec, "license")
    ET.SubElement(xrec, "optout").text = "false"
    ET.SubElement(ret, "persons")
    links = ET.SubElement(ret, "links")
    if event.videolink is not None:
        ET.SubElement(links, "link", href=event.videolink)
    if event.tickets_link is not None:
        ET.SubElement(links, "link", href=event.tickets_link)
    for social in event.socials:
        ET.SubElement(links, "link", href=social.url)
    ET.SubElement(ret, "attachments")
    ET.SubElement(ret, "url").text = event.url
    ET.SubElement(links, "link", href=event.url)
    ET.SubElement(ret, "feedback_url").text = event.url  # httpURI
    return ret


def slugify(n: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", n.lower())


urls = {
    "dollars": "https://www.facebook.com/photo/?fbid=1060844235603739&set=ecnf.100050345183987",
    "onderbroek": "https://grotebroek.nl/lokatie/de-onderbroek/",
    "opstand": "https://www.de-opstand.nl/agenda/",
}


def custom2frab(event: CustomEvent) -> ET.Element:
    url = urls[event.location]
    event_date = date(2024, 7, 12) + timedelta(event.day)
    start = datetime.combine(event_date, event.start)
    end = datetime.combine(event_date, event.end)
    if start.hour < ROLLOVER_HOUR:
        start += timedelta(days=1)
    if end.hour < ROLLOVER_HOUR:
        end += timedelta(days=1)
    if start >= end:
        print(f"Warning: Event {event.name} starts at {start} and ends at {end}")
        end = start + timedelta(hours=1)
    room = event.location
    title = event.name
    ret = ET.Element("event")
    ret.set("id", str(event.id))
    ret.set("guid", str(generate_deterministic_uuid(start, room, title)))
    ET.SubElement(ret, "date").text = start.strftime("%Y-%m-%dT%H:%M:00+02:00")
    ET.SubElement(ret, "start").text = start.strftime("%H:%M")
    duration_minutes = (end - start).seconds // 60
    duration_hours = duration_minutes // 60
    ET.SubElement(
        ret, "duration"
    ).text = f"{duration_hours:02}:{duration_minutes % 60:02}"
    ET.SubElement(ret, "room").text = room
    ET.SubElement(ret, "title").text = title
    ET.SubElement(ret, "description").text = event.description
    ET.SubElement(ret, "abstract").text = event.summary
    ET.SubElement(ret, "type").text = "performance"
    if event.location:
        ET.SubElement(ret, "track").text = event.location
    ET.SubElement(ret, "language")  # .text = "en"
    slug = f"{event.location}-{event.day}-{slugify(event.name)}"
    ET.SubElement(ret, "slug").text = f"vierdaagsef-2024-{event.id!s}-{slug}"
    ET.SubElement(ret, "subtitle")  # xs:string
    xrec = ET.SubElement(ret, "recording")
    ET.SubElement(xrec, "license")
    ET.SubElement(xrec, "optout").text = "false"
    ET.SubElement(ret, "persons")
    links = ET.SubElement(ret, "links")
    ET.SubElement(ret, "attachments")
    ET.SubElement(ret, "url").text = url
    ET.SubElement(links, "link", href=url)
    ET.SubElement(ret, "feedback_url").text = url  # httpURI
    return ret


def create_frab_xml(api: AllAPI, title="Vierdaagsefeesten", flt=lambda _: True):
    schedule = ET.Element("schedule")
    ET.SubElement(schedule, "version").text = "0.2"
    conference = ET.SubElement(schedule, "conference")
    start_date = min([x.date for x in api.days]).date()
    end_date = max([x.date for x in api.days]).date()
    ET.SubElement(conference, "acronym").text = "vierdaagsef-2024"
    ET.SubElement(conference, "title").text = title
    ET.SubElement(conference, "start").text = start_date.strftime("%Y-%m-%d")
    ET.SubElement(conference, "end").text = end_date.strftime("%Y-%m-%d")
    ET.SubElement(conference, "days").text = str(len(api.days))
    ET.SubElement(conference, "timeslot_duration").text = "00:15"

    xdays: list[tuple[ET.Element, defaultdict[str, list[ET.Element]]]] = []
    for d in range(1, 8):
        date = (start_date + timedelta(days=d - 1)).strftime("%Y-%m-%d")
        day = ET.SubElement(schedule, "day", date=date, index=str(d))
        day.set("start", f"{date}T09:00:00+02:00")
        day.set("end", f"{date}T23:59:00+02:00")  # TODO: use rollover hour
        xdays.append((day, defaultdict(list)))

    for program in api.programs:
        if not program.location:
            continue
        if flt(program):
            event = event2frab(program)
            day_ix = api.day_ix_by_id(program.day.id)
            _, xrooms = xdays[day_ix]
            loc_name = render_location_name(program.location.get())
            xrooms[loc_name].append(event)

    for cevent in parse_custom_events():
        event = custom2frab(cevent)
        _, xrooms = xdays[cevent.day - 1]
        xrooms[cevent.location].append(event)

    # sort rooms by the number of events in their parents
    c = Counter()
    all_rooms = set()
    for _, xr in xdays:
        for room, events in xr.items():
            all_rooms.add(room)
            c[room.split(" - ")[0]] += len(events)

    sorted_rooms = sorted(all_rooms, key=lambda x: (-c[x.split(" - ")[0]], x))
    for xd, xr in xdays:
        for r in sorted_rooms:
            room_elt = ET.SubElement(xd, "room", name=r)
            room_elt.extend(xr[r])

    return ET.ElementTree(schedule)


class CustomEvent(BaseModel):
    location: str
    day: int
    name: str
    start: time
    end: time
    summary: str = ""
    id: int
    description: str | None = None


def parse_custom_events() -> list[CustomEvent]:
    import csv

    i = 1000000
    res: list[CustomEvent] = []
    for datafile in Path("data").iterdir():
        loc = datafile.with_suffix("").name
        with datafile.open() as f:
            for j in csv.DictReader(f):
                res.append(CustomEvent(id=i, location=loc, **j))  # type: ignore[reportArgumentType]
                i += 1
    return res


parse_custom_events()
# TODO: download https://www.vierdaagsefeesten.nl/api/all


def main(
    input_file: Path, output_file: Path, name: str, *, only_interesting: bool = False
):
    api = load_api(input_file)
    api_result.set(api)
    xml_tree = create_frab_xml(
        api, name, filter_interesting if only_interesting else lambda _: True
    )
    xml_tree.write(output_file, encoding="UTF-8", xml_declaration=True)
    print(f"Frab XML file has been created: {output_file}")


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("input_file", type=Path)
    argparser.add_argument("output_file", type=Path)
    argparser.add_argument("--only-interesting", action="store_true")
    argparser.add_argument("--name", type=str, default="Vierdaagsefeesten")
    args = argparser.parse_args()
    main(
        args.input_file,
        args.output_file,
        args.name,
        only_interesting=args.only_interesting,
    )
