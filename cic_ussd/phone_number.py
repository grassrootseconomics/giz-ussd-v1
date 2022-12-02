# standard imports

# third-party imports
import contextlib
import phonenumbers


class E164Format:
    region = None


def process_phone_number(phone_number: str, region: str, add_plus: bool = True) -> str:
    """This function parses any phone number for the provided region
    :param add_plus: Adds a + symbol in front of the phone number.
    :type add_plus: bool
    :param phone_number: A string with a phone number.
    :type phone_number: str
    :param region: Caller defined region
    :type region: str
    :return: The parsed phone number value based on the defined region
    :rtype: str
    """
    if not isinstance(phone_number, str):
        with contextlib.suppress(ValueError):
            phone_number = str(int(phone_number))

    phone_number_object = phonenumbers.parse(phone_number, region)
    formatted_phone_number = phonenumbers.format_number(phone_number_object, phonenumbers.PhoneNumberFormat.E164)
    return formatted_phone_number if add_plus else formatted_phone_number.strip("+")


class Support:
    phone_number = None


class OfficeSender:
    tag = None
