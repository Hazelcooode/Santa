"""Search market is separate from the user's actual country/location."""
from .errors import ApiError

# ISO 3166-1 alpha-2 countries/territories. EU is a region, not a country bias.
COUNTRIES = frozenset('''AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'''.split())
SCOPES = ('country', 'eu', 'multiple', 'worldwide')


def validate(country, scope='country', countries=None):
    country = str(country or '').strip().upper()
    scope = str(scope or 'country').lower()
    if country not in COUNTRIES:
        raise ApiError(400, 'INVALID_COUNTRY', 'Enter a real country code, such as FI or DE. EU is a search scope, not a country code; select EU separately. Use GB for the United Kingdom.')
    if scope not in SCOPES:
        raise ApiError(400, 'INVALID_SEARCH_SCOPE', 'Choose country, eu, multiple or worldwide.')
    chosen = list(dict.fromkeys(str(c).strip().upper() for c in (countries or [])))
    if len(chosen) > 10 or any(c not in COUNTRIES for c in chosen):
        raise ApiError(400, 'INVALID_SEARCH_COUNTRIES', 'Select up to 10 real country codes, for example FI, SE, DE.')
    if scope == 'multiple' and not chosen:
        raise ApiError(400, 'SEARCH_COUNTRIES_REQUIRED', 'Enter the countries to search, for example FI, SE, DE.')
    return country, scope, chosen


def location_bias(user):
    if user.get('search_scope', 'country') != 'country':
        return None  # Do not accidentally bias a cross-border search to home country.
    code = str(user.get('site_region') or user.get('country') or '').upper()
    return code if code in COUNTRIES else None


def area(user):
    scope = user.get('search_scope', 'country')
    if scope == 'eu':
        return 'European Union'
    if scope == 'multiple':
        return 'markets ' + ', '.join(user.get('search_countries') or [])
    if scope == 'worldwide':
        return 'worldwide'
    return str(user.get('city') or '')
