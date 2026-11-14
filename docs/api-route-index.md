# Current API route index

Generated from current OpenAPI. See [current behaviour](current-behavior.md).

| Method | Path | Function | Group |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | Login | account |
| POST | `/api/v1/auth/register` | Register | account |
| POST | `/api/v1/auth/logout` | Logout | account |
| GET | `/api/v1/auth/challenge` | Challenge | account |
| GET | `/api/v1/me` | Me | account |
| PATCH | `/api/v1/me/preferences` | Prefs | account |
| POST | `/api/v1/consents/{scope}` | Grant | account |
| DELETE | `/api/v1/consents/{scope}` | Revoke | account |
| GET | `/api/v1/usage` | Usage | account |
| POST | `/api/deals` | Deals | mobile-compatible |
| POST | `/api/explore` | Explore | mobile-compatible |
| POST | `/api/products` | Products | mobile-compatible |
| POST | `/api/medicine` | Medicine | mobile-compatible |
| POST | `/api/wellbeing` | Wellbeing | mobile-compatible |
| POST | `/api/chat` | Chat | mobile-compatible |
| GET | `/api/v1/dashboard` | Dashboard | organiser |
| GET | `/api/v1/state` | State | organiser |
| GET | `/api/v1/today` | Today | organiser |
| POST | `/api/v1/today/{deco}` | Today Done | organiser |
| GET | `/api/v1/shopping/items` | Items | organiser |
| POST | `/api/v1/shopping/items` | Add Item | organiser |
| PATCH | `/api/v1/shopping/items/{item_id}` | Patch Item | organiser |
| DELETE | `/api/v1/shopping/items/{item_id}` | Del Item | organiser |
| POST | `/api/v1/shopping/deals` | Deals | organiser |
| POST | `/api/v1/shopping/orders` | Order | organiser |
| GET | `/api/v1/shopping/proposals/{proposal_id}/print` | Print List | organiser |
| GET | `/api/v1/shopping/stores` | Stores | organiser |
| PUT | `/api/v1/shopping/stores` | Set Stores | organiser |
| GET | `/api/v1/devices` | Devices | organiser |
| PATCH | `/api/v1/devices/{key}` | Device | organiser |
| GET | `/api/v1/inventory/regulars` | Regulars | organiser |
| GET | `/api/v1/devices/{key}/frames` | Frames | organiser |
| POST | `/api/v1/devices/{key}/scan` | Scan | organiser |
| POST | `/api/v1/devices/{key}/observations` | Observe | organiser |
| GET | `/api/v1/shopping/trip` | Trip | organiser |
| PUT | `/api/v1/shopping/trip` | Set Trip | organiser |
| POST | `/api/v1/shopping/trip/book` | Book Trip | organiser |
| GET | `/api/v1/laundry` | Laundry State | organiser |
| POST | `/api/v1/laundry/bookings` | Laundry Book | organiser |
| DELETE | `/api/v1/laundry/bookings/{ident}` | Laundry Cancel | organiser |
| PUT | `/api/v1/laundry/wardrobe` | Wardrobe | organiser |
| GET | `/api/v1/calendar/events` | Cal Events | organiser |
| POST | `/api/v1/calendar/events` | Cal Add | organiser |
| DELETE | `/api/v1/calendar/events/{event_id}` | Cal Del | organiser |
| GET | `/api/v1/calendar/free-slots` | Cal Free | organiser |
| GET | `/api/v1/shopping/settings` | Shopping Settings | organiser |
| PUT | `/api/v1/shopping/settings` | Put Shopping Settings | organiser |
| POST | `/api/v1/shopping/prices/refresh` | Refresh Prices | organiser |
| GET | `/api/v1/shopping/prices/status` | Refresh Status | organiser |
| POST | `/api/v1/chat` | Chat | companion, health, safety |
| GET | `/api/v1/chat/history` | Chat History | companion, health, safety |
| POST | `/api/v1/chat/reach-out` | Reach Out | companion, health, safety |
| GET | `/api/v1/memories` | Memories | companion, health, safety |
| POST | `/api/v1/memories` | Add Memory | companion, health, safety |
| DELETE | `/api/v1/memories/{mid}` | Del Memory | companion, health, safety |
| GET | `/api/v1/companion/posts` | Posts | companion, health, safety |
| POST | `/api/v1/companion/posts/refresh` | Refresh Posts | companion, health, safety |
| GET | `/api/v1/social` | Social | companion, health, safety |
| PATCH | `/api/v1/social/{sid}` | Set Social | companion, health, safety |
| POST | `/api/v1/calls` | Call | companion, health, safety |
| GET | `/api/v1/health/summary` | Health Summary | companion, health, safety |
| POST | `/api/v1/health/vitals` | Vitals | companion, health, safety |
| POST | `/api/v1/health/wellbeing` | Wellbeing | companion, health, safety |
| POST | `/api/v1/health/medicine` | Medicine | companion, health, safety |
| POST | `/api/v1/health/medicine/orders` | Med Order | companion, health, safety |
| GET | `/api/v1/health/appointments/suggestions` | Appt Suggestions | companion, health, safety |
| POST | `/api/v1/health/appointments` | Appt Book | companion, health, safety |
| GET | `/api/v1/health/rides/options` | Ride Options | companion, health, safety |
| POST | `/api/v1/health/rides` | Ride | companion, health, safety |
| GET | `/api/v1/safety/checkin` | Checkin Status | companion, health, safety |
| POST | `/api/v1/safety/checkin` | Checkin | companion, health, safety |
| PATCH | `/api/v1/safety/checkin` | Checkin Config | companion, health, safety |
| GET | `/api/v1/safety/checkin/missed-preview` | Missed Preview | companion, health, safety |
| POST | `/api/v1/safety/checkin/evaluate` | Evaluate | companion, health, safety |
| GET | `/api/v1/safety/locations` | Locations | companion, health, safety |
| POST | `/api/v1/safety/locations` | Location | companion, health, safety |
| POST | `/api/v1/safety/sos` | Sos | companion, health, safety |
| GET | `/api/v1/safety/sos/active` | Sos Active | companion, health, safety |
| POST | `/api/v1/safety/sos/{sos_id}/resolve` | Sos Resolve | companion, health, safety |
| GET | `/api/v1/safety/door/events` | Door Events | companion, health, safety |
| POST | `/api/v1/safety/door/events` | Door Ingest | companion, health, safety |
| POST | `/api/v1/safety/door/events/{event_id}/review` | Door Review | companion, health, safety |
| PATCH | `/api/v1/safety/door/settings` | Door Settings | companion, health, safety |
| GET | `/api/v1/contacts` | Contacts | companion, health, safety |
| POST | `/api/v1/contacts` | Add Contact | companion, health, safety |
| PATCH | `/api/v1/contacts/{cid}` | Patch Contact | companion, health, safety |
| DELETE | `/api/v1/contacts/{cid}` | Del Contact | companion, health, safety |
| GET | `/api/v1/outbox` | Outbox | companion, health, safety |
| POST | `/api/v1/explore` | Explore | research |
| POST | `/api/v1/products/search` | Products | research |
| POST | `/api/v1/tasks` | Create Task | research |
| GET | `/api/v1/tasks/{tid}` | Get Task | research |
| POST | `/api/v1/tasks/{tid}/clarifications` | Clarify | research |
| POST | `/api/v1/tasks/{tid}/cancel` | Cancel | research |
| GET | `/api/v1/tasks/{tid}/proposals` | Task Proposals | research |
| GET | `/api/v1/tasks/{tid}/export` | Export | research |
| GET | `/api/v1/proposals/{pid}` | Get Proposal | research |
| POST | `/api/v1/proposals/{pid}/approve` | Approve | research |
| GET | `/api/v1/actions/{aid}` | Action | research |
| GET | `/api/v1/bookings` | Bookings | research |
| GET | `/api/v1/price-watches` | List Watches | research |
| POST | `/api/v1/price-watches` | Create Watch | research |
| PATCH | `/api/v1/price-watches/{wid}` | Patch Watch | research |
| DELETE | `/api/v1/price-watches/{wid}` | Delete Watch | research |
| POST | `/api/v1/price-watches/{wid}/checks` | Check Watch | research |
| GET | `/api/v1/price-watches/{wid}/history` | Watch History | research |
| GET | `/api/v1/media` | List Media | research |
| POST | `/api/v1/media/rotation` | Rotation | research |
| POST | `/api/v1/media/itinerary` | Itinerary | research |
| POST | `/api/v1/media/event-teaser` | Teaser | research |
| POST | `/api/v1/price-watches/{wid}/options` | Save Watch Options | research |
| POST | `/api/v1/price-watches/{wid}/options/{oid}/rotation` | Rotate Watch Option | research |
| GET | `/api/v1/research-searches` | Saved Searches | research |
| GET | `/api/v1/itineraries` | Saved Trips | research |
| POST | `/api/v1/itineraries` | Save Trip | research |
| DELETE | `/api/v1/itineraries/{pid}` | Delete Trip | research |
| POST | `/api/v1/itineraries/{pid}/media` | Plan Media | research |
| GET | `/api/v1/itineraries/{pid}/print` | Print Itinerary | research |
| GET | `/api/v1/itineraries/{pid}/calendar` | Export Itinerary Calendar | research |
| POST | `/api/v1/price-watch-research` | Research Price Watch | research |
| POST | `/api/v1/price-watch-lists` | Save Researched List | research |
| GET | `/api/v1/media/{mid}/playback` | Play Media | research |
| GET | `/api/v1/integrations` | Status | integrations |
| POST | `/api/v1/integrations/{provider}/check` | Check | integrations |
| POST | `/api/v1/visual-previews` | Start Temporary Visual Preview | research |
| GET | `/api/v1/visual-previews/{sid}` | Preview Status | research |
| DELETE | `/api/v1/visual-previews/{sid}` | Close Preview | research |
| GET | `/api/v1/visual-previews/{sid}/content` | Owned Preview Stream / Download | research |
| GET | `/api/v1/product-images/{key}` | Clean Product Image | research |

129 operations.
