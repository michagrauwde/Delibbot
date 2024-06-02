# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


from datetime import datetime
from definitions import (DATABASE_HOST, DATABASE_PASSWORD, 
                         DATABASE_PORT, DATABASE_USER)
from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import FollowupAction, SlotSet
from typing import Any, Dict, List, Optional, Text

import logging
import mysql.connector


class ActionEndDialog(Action):
    """Action to cleanly terminate the dialog."""
    # ATM this action just call the default restart action
    # but this can be used to perform actions that might be needed
    # at the end of each dialog
    def name(self):
        return "action_end_dialog"

    async def run(self, dispatcher, tracker, domain):

        return [FollowupAction('action_restart')]


class ActionDefaultFallbackEndDialog(Action):
    """Executes the fallback action and goes back to the previous state
    of the dialogue"""

    def name(self) -> Text:
        return "action_default_fallback_end_dialog"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(template="utter_default")
        dispatcher.utter_message(template="utter_default_close_session")

        # End the dialog, which leads to a restart.
        return [FollowupAction('action_end_dialog')]
    

def get_latest_bot_utterance(events) -> Optional[Any]:
    """
       Get the latest utterance sent by the VC.
        Args:
            events: the events list, obtained from tracker.events
        Returns:
            The name of the latest utterance
    """
    events_bot = []

    for event in events:
        if event['event'] == 'bot':
            events_bot.append(event)

    if (len(events_bot) != 0
            and 'metadata' in events_bot[-1]
            and 'utter_action' in events_bot[-1]['metadata']):
        last_utterance = events_bot[-1]['metadata']['utter_action']
    else:
        last_utterance = None

    return last_utterance


def save_sessiondata_entry(cur, conn, userid, session_num, response_type,
                           response_value, time):
    query = "INSERT INTO sessiondata(userid, session_num, response_type, response_value, time) VALUES(%s, %s, %s, %s, %s)"
    cur.execute(query, [userid, session_num, response_type,
                        response_value, time])
    conn.commit()


class ActionSaveSession(Action):
    def name(self):
        return "action_save_session"

    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        now = datetime.now()
        formatted_date = now.strftime('%Y-%m-%d %H:%M:%S')

        try:
            conn = mysql.connector.connect(
                user=DATABASE_USER,
                password=DATABASE_PASSWORD,
                host=DATABASE_HOST,
                port=DATABASE_PORT,
                database='db'
            )
            cur = conn.cursor(prepared=True)

            userid = tracker.current_state()['sender_id']
            session_num = tracker.get_slot("session_num")

            slots_to_save = ["chosen_option", "chosen_option_reason", "reflection_slot"]
            for slot in slots_to_save:

                save_sessiondata_entry(cur, conn, userid, session_num,
                                       slot, tracker.get_slot(slot),
                                       formatted_date)

        except mysql.connector.Error as error:
            logging.info("Error in save session: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()

        return []


class ValidatereflectionForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_reflection_form'

    def validate_reflection_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate reflection_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_reflection_slot':
            return {"reflection_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"reflection_slot": None}

        return {"reflection_slot": value}
    
class ValidatestakeholdersForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_stakeholders_form'

    def validate_stakeholders_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate stakeholders_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_stakeholders_slot':
            return {"stakeholders_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"stakeholders_slot": None}

        return {"stakeholders_slot": value}

class ValidatevitalvalueForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_vitalvalue_form'

    def validate_vitalvalue_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate vitalvalue_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_vitalvalue_slot':
            return {"vitalvalue_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"vitalvalue_slot": None}

        return {"vitalvalue_slot": value}

class ValidateethicalramForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_ethicalram_form'

    def validate_ethicalram_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate ethicalram_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_EthicalRam_slot':
            return {"ethicalram_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"ethicalram_slot": None}

        return {"ethicalram_slot": value}
    
class ValidateearlierdecForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_earlierdec_form'

    def validate_earlierdec_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate earlierdec_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_earlierdec_slot':
            return {"earlierdec_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"earlierdec_slot": None}

        return {"earlierdec_slot": value}

class ValidatestakeholderdisForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_stakeholderdis_form'

    def validate_stakeholderdis_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate stakeholderdis_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_stakeholderdis_slot':
            return {"stakeholderdis_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"stakeholderdis_slot": None}

        return {"stakeholderdis_slot": value}
    
class ValidateexplorealtForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_explorealt_form'

    def validate_explorealt_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate explorealt_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_explorealt_slot':
            return {"explorealt_slot": None}

        # people should type a bit more
        if not len(value) >= 10:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"explorealt_slot": None}

        return {"explorealt_slot": value}
    
    