# standard imports

# external imports

# local imports


def gender():
    return {
        '1': 'male',
        '2': 'female',
        '3': 'other'
    }


def language():
    return {
        '1': 'en',
        '2': 'sw'
    }


def village_token():
    return {
        "Batoufam": "MBIP",
        "Bameka": "MUN",
        "Fondjomokwet": "MBA"
    }


def economic_activity():
    return {
        '1': 'agricultural_production',
        '2': 'service_provision',
        '3': 'commerce',
        '15': 'other'
    }


def yes_no():
    return {
        '1': 'yes',
        '2': 'no'
    }


def monthly_expenditure():
    return {
        '1': '0-20000',
        '2': '20000-35000',
        '3': 'More than 35000'
    }


def twenty_thousand_band():
    return {
        '1': '0-10000',
        '2': '10000-15000',
        '3': '15000-20000'
    }


def thirty_five_thousand_band():
    return {
        '1': '20000-25000',
        '2': '25000-30000',
        '3': '30000-35000'
    }


def above_thirty_five_thousand_band():
    return {
        '1': '35000-40000',
        '2': '40000-45000',
        '3': '45000-50000'
    }
