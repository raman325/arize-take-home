"""Pydantic schemas shared across pipeline steps."""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field


# --- Pipeline I/O ---


class NapWindow(BaseModel):
    start: time
    end: time

    def overlaps(self, slot_start: time, slot_end: time) -> bool:
        return slot_start < self.end and slot_end > self.start


class Constraints(BaseModel):
    """What the constraint-extraction step produces from the family request."""

    child_age_years: float
    nap_window_saturday: NapWindow | None = None
    nap_window_sunday: NapWindow | None = None
    preferences: list[str] = Field(default_factory=list)
    free_windows_saturday: list[tuple[time, time]] = Field(default_factory=list)
    free_windows_sunday: list[tuple[time, time]] = Field(default_factory=list)
    notes: str = ""


# --- Tools (weather + calendar) ---


class DayForecast(BaseModel):
    day: Literal["Saturday", "Sunday"]
    condition: Literal["sunny", "cloudy", "rain", "snow"]
    high_f: int
    low_f: int
    precip_chance: int  # 0-100
    outdoor_friendly: bool


class WeatherForecast(BaseModel):
    saturday: DayForecast
    sunday: DayForecast


class CalendarEvent(BaseModel):
    day: Literal["Saturday", "Sunday"]
    start: time
    end: time
    title: str


class CalendarLookup(BaseModel):
    events: list[CalendarEvent]


# --- Activity catalog ---


class Activity(BaseModel):
    id: str
    name: str
    description: str  # what gets embedded
    indoor: bool
    min_age_years: float
    max_age_years: float
    typical_duration_min: int
    travel_minutes_from_home: int  # one-way
    tags: list[str]


# --- Retrieval + ranking ---


class RetrievedActivity(BaseModel):
    activity: Activity
    similarity_score: float  # 0-1 cosine sim


class RankedCandidate(BaseModel):
    activity: Activity
    similarity_score: float
    suitability_score: float  # post-filter rank score
    filter_reasons: list[str] = Field(default_factory=list)  # why it was kept/dropped


# --- Plan ---


class PlanSlot(BaseModel):
    day: Literal["Saturday", "Sunday"]
    start: time
    end: time
    activity_id: str
    activity_name: str
    notes: str = ""

    def duration_min(self) -> int:
        sm = self.start.hour * 60 + self.start.minute
        em = self.end.hour * 60 + self.end.minute
        return em - sm


class WeekendPlan(BaseModel):
    saturday: list[PlanSlot]
    sunday: list[PlanSlot]
    summary: str = ""

    def all_slots(self) -> list[PlanSlot]:
        return [*self.saturday, *self.sunday]
