"""
Agent flow tests with a fake LLM and fake map data (no network access):
location / date / currency resolution, planning, validation, repair,
replanning, fallbacks and the HTTP API.
"""

import json
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.agent.planner import PlanningAgent
from app.geo import geocoder, places
from app.geo.geocoder import Place
from app.llm.client import LLMUnavailableError
from app.models.schemas import PlanState, ResponseStatus

JAIPUR = Place(name="Jaipur", display_name="Jaipur, Rajasthan, India", lat=26.9154, lon=75.8189,
               country="India", country_code="in", radius_m=9000)
PARIS = Place(name="Paris", display_name="Paris, France", lat=48.8535, lon=2.3484,
              country="France", country_code="fr", radius_m=9000)
CAMBRIDGE = Place(name="Cambridge", lat=52.1976, lon=0.1392, country="United Kingdom",
                  country_code="gb", radius_m=6000)
KNOWN = {"jaipur": JAIPUR, "paris": PARIS, "cambridge": CAMBRIDGE}

LIVE = {
    "attraction": [
        {"name": "Amber Fort", "type": "castle", "source": "openstreetmap", "lat": 26.98, "lon": 75.85,
         "map_url": "https://www.openstreetmap.org/way/1"},
        {"name": "City Palace", "type": "palace", "source": "openstreetmap"},
        {"name": "Hawa Mahal", "type": "attraction", "source": "openstreetmap", "entrance_fee": "free"},
        {"name": "Jantar Mantar", "type": "attraction", "source": "openstreetmap"},
    ],
    "restaurant": [
        {"name": "Green Leaf", "type": "restaurant", "vegetarian": "yes", "source": "openstreetmap"},
        {"name": "Spice Court", "type": "restaurant", "source": "openstreetmap"},
        {"name": "Thali House", "type": "restaurant", "source": "openstreetmap"},
        {"name": "Lassi Corner", "type": "cafe", "source": "openstreetmap"},
    ],
    "hotel": [{"name": "Hotel Kalyan", "type": "hotel", "stars": "3", "source": "openstreetmap"}],
    "transport": [{"name": "Jaipur Junction", "type": "railway station", "source": "openstreetmap"}],
}


class FakeLLM:
    """Stands in for LLMClient. `plan` is returned for structured Plan requests."""

    def __init__(self, plan: Optional[Dict[str, Any]] = None, frugal: bool = True, fail: bool = False):
        self.plan = plan
        self.frugal = frugal
        self.fail = fail
        self.last_provider = "fake"
        self.providers: List[Any] = []
        self.prompts: List[str] = []

    def generate(self, prompt, system=None, temperature=0.3, max_tokens=4096, json_mode=False, history=None):
        self.prompts.append(prompt)
        if self.fail:
            raise LLMUnavailableError("down")
        return "Here is what I found."

    def generate_structured(self, prompt, schema, system=None, temperature=0.1):
        self.prompts.append(prompt)
        if self.fail or self.plan is None:
            raise LLMUnavailableError("down")
        return schema.model_validate(json.loads(json.dumps(self.plan)))


def activity(name, kind, cost, start="10:00", **details):
    return {"name": name, "type": kind, "estimated_cost": cost, "start_time": start, "details": details}


def day(number, morning, afternoon, evening):
    return {"day": number, "slots": [
        {"time_of_day": "morning", "activities": morning},
        {"time_of_day": "afternoon", "activities": afternoon},
        {"time_of_day": "evening", "activities": evening},
    ]}


def two_day_plan(expensive=False):
    dinner = 9000 if expensive else 400
    return {
        "summary": "Two days of forts and food.",
        "location": "somewhere else", "duration_days": 2, "estimated_total_cost": 1,
        "days": [
            day(1, [activity("Amber Fort", "attraction", 200, "09:00", note="Go early")],
                [activity("Green Leaf", "restaurant", 300, "13:00")],
                [activity("Spice Court", "restaurant", dinner, "19:30"),
                 activity("Hotel Kalyan", "hotel", 2000, "21:00")]),
            day(2, [activity("City Palace", "attraction", 300, "09:30")],
                [activity("Thali House", "restaurant", 350, "13:00"),
                 activity("Nahargarh Sunset Point", "attraction", 0, "17:00")],
                [activity("Lassi Corner", "restaurant", 150, "19:00")]),
        ],
    }


@pytest.fixture(autouse=True)
def fake_world(monkeypatch):
    """Geocoding and live places answer from fixtures."""
    def fake_geocode(query):
        return KNOWN.get(str(query).strip().lower().split(",")[0])

    monkeypatch.setattr(geocoder, "geocode", fake_geocode)
    monkeypatch.setattr(geocoder, "reverse", lambda lat, lon: JAIPUR.model_copy(
        update={"lat": lat, "lon": lon, "kind": "current_location"}))
    monkeypatch.setattr(geocoder, "lookup", lambda lat, lon: next(
        (p for p in KNOWN.values() if abs(p.lat - lat) < 0.01 and abs(p.lon - lon) < 0.01), None))
    monkeypatch.setattr(geocoder, "service_ok", lambda: True)
    monkeypatch.setattr(
        places, "fetch_places",
        lambda place, domains: {d: [dict(r) for r in LIVE.get(d, [])] for d in domains},
    )


def agent_with(plan=None, **kwargs) -> PlanningAgent:
    return PlanningAgent(llm_client=FakeLLM(plan=plan, **kwargs))


class TestFallbackIntent:
    @pytest.mark.parametrize("message,intent", [
        ("Find me a cheap hotel in Paris", "hotel_search"),
        ("vegetarian restaurants in Jaipur", "restaurant_search"),
        ("What are the top attractions in Paris?", "attraction_search"),
        ("Show railway stations near Jaipur", "transport_search"),
        ("Plan a 3-day trip to Jaipur", "trip_planning"),
        ("3 days in Goa", "trip_planning"),
        ("hotels in Paris within 3 days", "hotel_search"),
        ("Create a study schedule for maths", "study_planning"),
        ("What is the best time of year to visit Kerala?", "general_query"),
        ("hello there", "general_query"),
    ])
    def test_intent(self, message, intent):
        assert agent_with()._fallback_intent(message, PlanState()).intent == intent

    @pytest.mark.parametrize("message,budget", [
        ("trip under 5000 rupees", 5000.0), ("budget of ₹12,000", 12000.0),
        ("spend 15k rupees", 15000.0), ("£200 weekend", 200.0),
        ("Plan a 2 day trip", None), ("finish within 3 days", None), ("under 3 days", None),
        ("arrive before 10:00", None),
    ])
    def test_budget(self, message, budget):
        assert agent_with()._fallback_intent(message, PlanState()).budget == budget

    @pytest.mark.parametrize("message,location", [
        ("Plan a trip to New Delhi for 2 days", "new delhi"),
        ("hotels in paris with wifi", "paris"),
        ("restaurants near me", None),
        ("find hotels in the centre", None),
        ("Plan a 2-day trip", None),
    ])
    def test_location(self, message, location):
        assert agent_with()._fallback_intent(message, PlanState()).location == location

    def test_dates_preferences_and_currency(self):
        res = agent_with()._fallback_intent(
            "Plan a vegetarian weekend trip to Jaipur from 2026-12-12 to 2026-12-13 under 9000 rupees",
            PlanState())
        assert (res.start_date, res.end_date) == ("2026-12-12", "2026-12-13")
        assert res.duration_days == 2 and "vegetarian" in res.preferences and res.currency == "INR"


class TestLocationAndDates:
    def test_search_without_location_asks(self):
        state = PlanState()
        res = agent_with().handle_message("Find me a hotel", state)
        assert res.status == ResponseStatus.CLARIFICATION_REQUIRED
        assert "where" in res.message.lower()

    def test_unknown_place_is_reported(self):
        res = agent_with().handle_message("Plan a 2 day trip to Qwzxplace", PlanState())
        assert res.status == ResponseStatus.CLARIFICATION_REQUIRED
        assert "couldn't find" in res.message.lower()

    def test_ui_location_is_used_when_message_names_none(self):
        state = PlanState()
        res = agent_with().handle_message(
            "Find restaurants", state,
            {"location": "Paris, France", "lat": PARIS.lat, "lon": PARIS.lon, "explicit": True})
        assert res.status == ResponseStatus.COMPLETED
        assert res.context["currency"] == "EUR"
        assert res.results_domain == "restaurant" and len(res.results) == 4
        assert res.context["data_source"] == "openstreetmap"

    def test_message_location_beats_ui_location(self):
        state = PlanState()
        res = agent_with().handle_message(
            "Find hotels in Jaipur", state,
            {"location": "Paris, France", "lat": PARIS.lat, "lon": PARIS.lon})
        assert res.context["location"] == "Jaipur, India" and res.context["currency"] == "INR"

    def test_near_me_uses_device_position(self):
        state = PlanState(location="Paris, France", place={**PARIS.model_dump(), "label": "Paris, France"})
        res = agent_with().handle_message(
            "restaurants near me", state, {"location": "Jaipur, India", "lat": 26.9, "lon": 75.8})
        assert res.context["location"] == "Jaipur, India"

    def test_dates_from_ui_set_duration_and_day_dates(self):
        state = PlanState()
        res = agent_with(two_day_plan()).handle_message(
            "Plan a trip to Jaipur", state,
            {"start_date": "2026-12-12", "end_date": "2026-12-13", "explicit": True})
        assert res.status == ResponseStatus.COMPLETED
        assert [d.date for d in res.plan.days] == ["2026-12-12", "2026-12-13"]
        assert (res.plan.start_date, res.plan.end_date) == ("2026-12-12", "2026-12-13")
        assert state.duration_days == 2

    def test_reversed_and_overlong_dates_are_normalised(self):
        agent = agent_with()
        state = PlanState()
        agent._resolve_dates(state, agent._fallback_intent("trip", state),
                             {"start_date": "2026-12-20", "end_date": "2026-12-18"})
        assert (state.start_date, state.end_date, state.duration_days) == ("2026-12-18", "2026-12-20", 3)

        state = PlanState()
        agent._resolve_dates(state, agent._fallback_intent("trip", state),
                             {"start_date": "2026-01-01", "end_date": "2026-03-01"})
        assert state.duration_days == 14 and state.end_date == "2026-01-14"

    def test_stated_duration_overrides_ui_range(self):
        agent = agent_with()
        state = PlanState()
        agent._resolve_dates(state, agent._fallback_intent("a 4 day trip", state),
                             {"start_date": "2026-12-10", "end_date": "2026-12-11"})
        assert state.duration_days == 4 and state.end_date == "2026-12-13"

    def test_invalid_dates_are_ignored(self):
        agent = agent_with()
        state = PlanState()
        agent._resolve_dates(state, agent._fallback_intent("trip", state),
                             {"start_date": "not-a-date", "end_date": "2026-02-31"})
        assert state.start_date is None and state.end_date is None


class TestPlanning:
    def test_plan_is_grounded_and_totals_are_computed(self):
        state = PlanState()
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur with a budget of 12000 rupees", state)
        assert res.status == ResponseStatus.COMPLETED
        plan = res.plan
        assert plan.location == "Jaipur, India" and plan.currency == "INR"
        assert plan.estimated_total_cost == 200 + 300 + 400 + 2000 + 300 + 350 + 0 + 150
        fort = plan.days[0].slots[0].activities[0]
        assert fort.details["source"] == "openstreetmap" and fort.details["note"] == "Go early"
        assert fort.details["map_url"].startswith("https://www.openstreetmap.org/")
        assert "₹" in res.message and "Day 2" in res.message

    def test_ungrounded_place_is_flagged_as_ai_suggestion(self):
        res = agent_with(two_day_plan()).handle_message("Plan a 2 day trip to Jaipur", PlanState())
        sunset = res.plan.days[1].slots[1].activities[1]
        assert sunset.details["source"] == "ai_suggested"
        assert any("Nahargarh Sunset Point" in w for w in res.validation.warnings)

    def test_over_budget_plan_is_repaired_deterministically(self):
        state = PlanState()
        res = agent_with(two_day_plan(expensive=True)).handle_message(
            "Plan a 2 day trip to Jaipur with a budget of 5000 rupees", state)
        assert res.status == ResponseStatus.COMPLETED
        assert res.plan.estimated_total_cost <= 5000
        names = [a.name for d in res.plan.days for s in d.slots for a in s.activities]
        assert "Spice Court" not in names
        assert all(sum(len(s.activities) for s in d.slots) > 0 for d in res.plan.days)

    def test_impossible_budget_reports_constraint_failure(self):
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur with a budget of 100 rupees", PlanState())
        assert res.status == ResponseStatus.CONSTRAINT_FAILURE
        assert res.validation.valid is False and res.plan is not None

    def test_wrong_day_count_is_fixed(self):
        res = agent_with(two_day_plan()).handle_message("Plan a 3 day trip to Jaipur", PlanState())
        assert res.status == ResponseStatus.COMPLETED and len(res.plan.days) == 3
        res = agent_with(two_day_plan()).handle_message("Plan a 1 day trip to Jaipur", PlanState())
        assert res.status == ResponseStatus.COMPLETED and len(res.plan.days) == 1

    def test_llm_down_builds_plan_from_live_data(self):
        state = PlanState()
        res = agent_with(fail=True).handle_message("Plan a 2 day trip to Jaipur", state)
        assert res.status == ResponseStatus.COMPLETED and len(res.plan.days) == 2
        names = {a.name for d in res.plan.days for s in d.slots for a in s.activities}
        assert "Amber Fort" in names and "Green Leaf" in names
        assert "notice" in res.context

    def test_llm_down_search_still_lists_live_results(self):
        res = agent_with(fail=True).handle_message("hotels in Jaipur", PlanState())
        assert res.status == ResponseStatus.COMPLETED
        assert "Hotel Kalyan" in res.message and res.results[0]["name"] == "Hotel Kalyan"

    def test_no_results_and_llm_down_is_honest(self, monkeypatch):
        monkeypatch.setattr(places, "fetch_places", lambda place, domains: {d: [] for d in domains})
        res = agent_with(fail=True).handle_message("hotels in Jaipur", PlanState())
        assert res.status == ResponseStatus.COMPLETED and res.results == []
        assert "couldn't find" in res.message.lower()

    def test_study_plan_without_llm(self):
        res = agent_with(fail=True).handle_message(
            "Create a 3-day study schedule for maths and physics with breaks", PlanState())
        assert res.status == ResponseStatus.COMPLETED
        assert res.plan.plan_type == "study" and len(res.plan.days) == 3
        assert res.plan.estimated_total_cost is None
        names = {a.name for d in res.plan.days for s in d.slots for a in s.activities}
        assert {"Maths", "Physics"} <= names

    def test_general_question_and_llm_outage(self):
        res = agent_with().handle_message("What is the best time of year to visit Kerala?", PlanState())
        assert res.status == ResponseStatus.COMPLETED and res.plan is None and res.results == []
        res = agent_with(fail=True).handle_message("hello", PlanState())
        assert res.status == ResponseStatus.COMPLETED and "busy" in res.message

    def test_cambridge_uses_bundled_dataset_with_area(self):
        res = agent_with(fail=True).handle_message("Find cheap hotels in the centre of Cambridge", PlanState())
        assert res.status == ResponseStatus.COMPLETED and res.results
        assert res.context["currency"] == "GBP" and res.context["data_source"] == "multiwoz"
        assert all(r["area"] == "centre" and r["pricerange"] == "cheap" for r in res.results)

    def test_cambridge_trains(self):
        res = agent_with(fail=True).handle_message(
            "Find trains from Cambridge to London Kings Cross", PlanState())
        assert res.results and all(
            r["departure"] == "cambridge" and r["destination"] == "london kings cross" for r in res.results)


class TestReplanning:
    def _planned_state(self):
        state = PlanState()
        agent = agent_with(two_day_plan())
        res = agent.handle_message("Plan a 2 day trip to Jaipur with a budget of 12000 rupees", state)
        assert res.status == ResponseStatus.COMPLETED
        return agent, state

    def test_budget_change_in_chat(self):
        agent, state = self._planned_state()
        res = agent.handle_message("Change the budget to 1500 rupees", state)
        assert state.budget == 1500 and state.intent == "trip_planning"
        assert res.plan is not None and len(res.plan.days) == 2
        if res.status == ResponseStatus.COMPLETED:
            assert res.plan.estimated_total_cost <= 1500

    def test_replan_api_changes_duration(self):
        agent, state = self._planned_state()
        res = agent.replan_with_changes(state, {"duration_days": 1})
        assert res.status == ResponseStatus.COMPLETED and len(res.plan.days) == 1
        assert state.replan_count == 1

    def test_new_destination_refetches_data(self):
        agent, state = self._planned_state()
        res = agent.handle_message("Plan a 2 day trip to Paris", state)
        assert res.context["location"] == "Paris, France" and res.context["currency"] in ("INR", "EUR")
        assert res.plan.location == "Paris, France"


class TestApi:
    @pytest.fixture
    def client(self, monkeypatch):
        from app.main import app
        from app.services.session_service import session_service
        monkeypatch.setattr(session_service, "_agent", agent_with(two_day_plan()))
        monkeypatch.setattr(geocoder, "search", lambda q, limit=5: [PARIS] if "par" in q.lower() else [])
        with TestClient(app) as test_client:
            yield test_client

    def test_health(self, client):
        data = client.get("/api/v1/health").json()
        assert data["status"] == "ok" and data["service"] == "planwise-api"
        assert "llm_available" in data and "limited_mode" in data

    def test_geo_endpoints(self, client):
        data = client.get("/api/v1/geo/search", params={"q": "Paris"}).json()
        assert data[0]["label"] == "Paris, France" and data[0]["currency"] == "EUR"
        assert client.get("/api/v1/geo/search", params={"q": "zzzz"}).json() == []
        assert client.get("/api/v1/geo/search", params={"q": "a"}).status_code == 422
        assert client.get("/api/v1/geo/reverse", params={"lat": 91, "lon": 0}).status_code == 422
        rev = client.get("/api/v1/geo/reverse", params={"lat": 26.9, "lon": 75.8}).json()
        assert rev["name"] == "Jaipur" and rev["currency"] == "INR"

    def test_message_validation(self, client):
        sid = client.post("/api/v1/sessions", json={}).json()["session_id"]
        url = f"/api/v1/sessions/{sid}/messages"
        assert client.post(url, json={"message": ""}).status_code == 422
        assert client.post(url, json={"message": "   "}).status_code == 422
        assert client.post(url, json={"message": "x" * 2001}).status_code == 422
        assert client.post(url, json={"message": "hi", "context": {"lat": 999, "lon": 0}}).status_code == 422
        assert client.post("/api/v1/sessions/unknown/messages", json={"message": "hi"}).status_code == 404
        assert client.get("/api/v1/sessions/unknown").status_code == 404
        assert client.get("/api/v1/sessions/unknown/plan").status_code == 404

    def test_full_conversation(self, client):
        sid = client.post("/api/v1/sessions", json={}).json()["session_id"]
        url = f"/api/v1/sessions/{sid}"
        assert client.post(f"{url}/replan", json={"changes": {"budget": 5}}).json()["status"] == "error"

        data = client.post(f"{url}/messages", json={
            "message": "Plan a trip to Jaipur",
            "context": {"start_date": "2026-12-12", "end_date": "2026-12-13", "explicit": True},
        }).json()
        assert data["status"] == "completed" and len(data["plan"]["days"]) == 2
        assert data["context"]["start_date"] == "2026-12-12"

        plan = client.get(f"{url}/plan").json()
        assert plan["plan"]["currency"] == "INR" and plan["validation"]["valid"] is True

        state = client.get(url).json()["state"]
        assert state["has_plan"] and state["duration_days"] == 2 and state["location"] == "Jaipur, India"

        data = client.post(f"{url}/replan", json={"changes": {"duration_days": 1}}).json()
        assert data["status"] == "completed" and len(data["plan"]["days"]) == 1


class TestGroupTravel:
    """Number of travellers: parsing, cost splitting and budget checks."""

    # two_day_plan(): per-person costs 200+300+400+300+350+0+150 = 1700,
    # plus one hotel night at 2000 per room.
    PER_PERSON_ACTIVITIES = 1700
    HOTEL_PER_ROOM = 2000

    @pytest.mark.parametrize("message,travelers", [
        ("Plan a trip to Goa for 4 people", 4),
        ("we are 3 friends going to Jaipur", 3),
        ("trip for six people to Paris", 6),
        ("a family of 5 visiting Mysuru", 5),
        ("we are 3 going to Jaipur", 3),
        ("hotels in Paris for 2 adults", 2),
        ("honeymoon in Bali", 2),
        ("a solo trip to Tokyo", 1),
        ("Plan a 3 day trip to Goa", None),
        ("we are 3 days in Goa", None),
    ])
    def test_travelers_parsing(self, message, travelers):
        assert agent_with()._fallback_intent(message, PlanState()).travelers == travelers

    def test_group_size_does_not_become_a_budget(self):
        res = agent_with()._fallback_intent("Plan a trip to Goa under 4 people", PlanState())
        assert res.budget is None

    def test_costs_are_split_and_rooms_shared(self):
        state = PlanState()
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur for 4 people with a budget of 20000 rupees", state)
        assert res.status == ResponseStatus.COMPLETED
        plan = res.plan
        expected_total = self.PER_PERSON_ACTIVITIES * 4 + self.HOTEL_PER_ROOM * 2
        assert plan.travelers == 4 and plan.rooms == 2
        assert plan.estimated_total_cost == expected_total
        assert plan.cost_per_person == expected_total / 4
        assert res.context["travelers"] == 4 and res.context["budget_per_person"] == 5000
        assert "4 travellers" in res.message and "per person" in res.message
        assert "2 rooms" in res.message

    def test_per_person_budget_is_multiplied_out(self):
        state = PlanState()
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur for 4 people, budget 5000 rupees each", state)
        assert state.budget == 20000 and res.status == ResponseStatus.COMPLETED

    def test_group_budget_is_checked_against_group_total(self):
        # group total 10800 > 9000: the most expensive item (hotel, 4000) is dropped
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur for 4 people with a budget of 9000 rupees", PlanState())
        assert res.status == ResponseStatus.COMPLETED
        assert res.plan.estimated_total_cost <= 9000
        names = [a.name for d in res.plan.days for s in d.slots for a in s.activities]
        assert "Hotel Kalyan" not in names

    def test_ui_selector_sets_group_size(self):
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur", PlanState(), {"travelers": 3})
        assert res.plan.travelers == 3 and res.plan.rooms == 2
        assert res.plan.estimated_total_cost == self.PER_PERSON_ACTIVITIES * 3 + self.HOTEL_PER_ROOM * 2

    def test_message_beats_ui_selector(self):
        res = agent_with(two_day_plan()).handle_message(
            "Plan a 2 day trip to Jaipur for 2 people", PlanState(), {"travelers": 5})
        assert res.plan.travelers == 2

    def test_solo_trip_shows_plain_total(self):
        res = agent_with(two_day_plan()).handle_message("Plan a 2 day trip to Jaipur", PlanState())
        assert res.plan.travelers == 1 and res.plan.rooms == 1
        assert res.plan.cost_per_person == res.plan.estimated_total_cost
        assert "travellers" not in res.message

    def test_changing_group_size_updates_existing_plan(self):
        state = PlanState()
        agent = agent_with(two_day_plan())
        first = agent.handle_message("Plan a 2 day trip to Jaipur", state)
        solo_total = first.plan.estimated_total_cost

        res = agent.handle_message("we are 4 people now", state)
        assert res.status == ResponseStatus.COMPLETED and res.plan is not None
        assert state.travelers == 4 and res.plan.travelers == 4
        assert res.plan.estimated_total_cost > solo_total
        assert len(res.plan.days) == 2

    def test_replan_api_changes_travelers(self):
        state = PlanState()
        agent = agent_with(two_day_plan())
        agent.handle_message("Plan a 2 day trip to Jaipur", state)
        res = agent.replan_with_changes(state, {"travelers": 3})
        assert res.status == ResponseStatus.COMPLETED and res.plan.travelers == 3

    def test_tight_budget_warning_is_per_person(self):
        from app.validation.constraints import check_impossible_constraints
        assert check_impossible_constraints(PlanState(budget=1000, duration_days=2, travelers=1)) == []
        warnings = check_impossible_constraints(PlanState(budget=1000, duration_days=2, travelers=4))
        assert warnings and "4 people" in warnings[0] and "/person/day" in warnings[0]

    def test_context_validation(self):
        from app.models.requests import MessageContext
        from pydantic import ValidationError
        assert MessageContext(travelers=4).travelers == 4
        for bad in (0, 51):
            with pytest.raises(ValidationError):
                MessageContext(travelers=bad)


class TestCancellation:
    """Stop button: a cancelled message leaves the session untouched."""

    class RecordingAgent:
        def __init__(self, service=None, cancel_id=None):
            self.service = service
            self.cancel_id = cancel_id

        def handle_message(self, message, state, context=None):
            if self.service and self.cancel_id:
                self.service.cancel(state.session_id, self.cancel_id)   # user pressed Stop mid-way
            state.goal = message
            state.travelers = 7
            from app.models.schemas import AgentResponse
            return AgentResponse(session_id=state.session_id, status=ResponseStatus.COMPLETED, message="done")

    def _service(self):
        from app.services.session_service import SessionService
        service = SessionService.__new__(SessionService)
        SessionService.__init__(service)
        return service

    def test_completed_request_is_committed(self):
        service = self._service()
        service._agent = self.RecordingAgent()
        sid = service.create_session()
        res = service.handle_message(sid, "plan a trip", request_id="r1")
        assert res.status == ResponseStatus.COMPLETED
        assert service.get_session(sid).goal == "plan a trip"

    def test_cancelled_request_is_discarded(self):
        service = self._service()
        sid = service.create_session()
        service._agent = self.RecordingAgent(service, "r2")
        res = service.handle_message(sid, "cancel me", request_id="r2")
        assert res.status == ResponseStatus.CANCELLED
        state = service.get_session(sid)
        assert state.goal is None and state.travelers == 1

        # the next (rewritten) message works normally
        service._agent = self.RecordingAgent()
        assert service.handle_message(sid, "rewritten", request_id="r3").status == ResponseStatus.COMPLETED
        assert service.get_session(sid).goal == "rewritten"

    def test_cancel_before_start_skips_the_work(self):
        service = self._service()
        sid = service.create_session()
        service.cancel(sid, "r4")
        service._agent = self.RecordingAgent()
        assert service.handle_message(sid, "x", request_id="r4").status == ResponseStatus.CANCELLED
        assert service.get_session(sid).goal is None

    def test_cancel_endpoint(self, monkeypatch):
        from app.main import app
        with TestClient(app) as client:
            sid = client.post("/api/v1/sessions", json={}).json()["session_id"]
            ok = client.post(f"/api/v1/sessions/{sid}/messages/abc-123/cancel")
            assert ok.status_code == 202 and ok.json()["status"] == "cancelled"
            assert client.post("/api/v1/sessions/nope/messages/abc/cancel").status_code == 404
            bad = client.post(f"/api/v1/sessions/{sid}/messages",
                              json={"message": "hi", "request_id": "bad id!"})
            assert bad.status_code == 422


class TestGroupSearchAndSparseData:
    """Stays / dining searches for a group, and towns with little map data."""

    def test_stay_search_on_existing_plan_is_a_search(self):
        state = PlanState()
        agent = agent_with(two_day_plan())
        agent.handle_message("Plan a 2 day trip to Jaipur", state)
        res = agent.handle_message("Show me best places to stay with proper budget for 13 people", state)
        assert res.status == ResponseStatus.COMPLETED
        assert res.results_domain == "hotel" and res.results
        assert state.travelers == 13
        # the existing plan was not rewritten
        assert state.current_plan is not None and state.current_plan.travelers == 1

    def test_hotel_results_carry_group_estimates(self):
        state = PlanState()
        res = agent_with(fail=True).handle_message("hotels in Jaipur for 13 people", state)
        hotel = res.results[0]
        rooms, nights = 7, 1
        assert hotel["est_group_cost"] == hotel["est_cost_per_person"] * 13 or \
            abs(hotel["est_group_cost"] / 13 - hotel["est_cost_per_person"]) < 0.01
        assert f"{rooms} rooms" in hotel["est_cost"] and f"{nights} night" in hotel["est_cost"]
        assert "13 travellers need about 7 rooms" in res.message

    def test_results_checked_against_group_budget(self):
        state = PlanState()
        res = agent_with(fail=True).handle_message(
            "restaurants in Jaipur for 4 people under 1000 rupees", state)
        assert all("within_budget" in r for r in res.results)
        flags = [r["within_budget"] for r in res.results]
        assert flags == sorted(flags, reverse=True)      # affordable first

    def test_budget_sets_price_level(self):
        agent = agent_with()
        tight = PlanState(budget=6000, travelers=4, duration_days=2, currency="INR")
        rich = PlanState(budget=400000, travelers=2, duration_days=2, currency="INR")
        assert agent._level_for_budget(tight) == "cheap"
        assert agent._level_for_budget(rich) == "expensive"
        assert agent._level_for_budget(PlanState()) == "moderate"

    def test_placeholder_days_do_not_zero_the_total(self, monkeypatch):
        sparse = {"attraction": [dict(LIVE["attraction"][0])], "restaurant": [], "hotel": []}
        monkeypatch.setattr(places, "fetch_places",
                            lambda place, domains: {d: [dict(r) for r in sparse.get(d, [])] for d in domains})
        res = agent_with(fail=True).handle_message("Plan a 3 day trip to Jaipur for 13 people", PlanState())
        assert res.plan is not None and len(res.plan.days) == 3
        assert res.plan.estimated_total_cost != 0


class TestPickedPlaceName:
    def test_picked_city_keeps_its_name(self, monkeypatch):
        neighbourhood = JAIPUR.model_copy(update={"name": "Manipal", "kind": "current_location"})
        monkeypatch.setattr(geocoder, "lookup", lambda lat, lon: None)
        monkeypatch.setattr(geocoder, "reverse", lambda lat, lon: neighbourhood)
        res = agent_with(fail=True).handle_message(
            "Find hotels", PlanState(),
            {"location": "Udupi, India", "lat": 13.34, "lon": 74.75, "explicit": True})
        assert res.context["location"].startswith("Udupi")
