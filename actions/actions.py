# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


from datetime import datetime
from definitions import (DATABASE_HOST, DATABASE_PASSWORD, 
                         DATABASE_PORT, DATABASE_USER, df_act,
                         MIN_CHAR_EXPERIENCE,
                         MIN_CHAR_EXPERIENCE_MOD,
                         MIN_CHAR_HUMAN_COACH_INTRO,
                         NUM_ACTIVITIES,
                         PROB_HUMAN_SUPPORT)
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import (ActionExecuted, FollowupAction, 
                             SessionStarted, SlotSet)
from string import Template
from typing import Any, Dict, List, Optional, Text

import logging
import mysql.connector
import random
import smtplib, ssl


class ActionSessionStart(Action):
    def name(self) -> Text:
        return "action_session_start"

    async def run(
      self, dispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        session_num = tracker.get_slot("session_num")

        # The session should begin with a `session_started` event
        # in case of a timed-out session, we also need this so that rasa does not
        # continue with uncompleted forms.
        events = [SessionStarted()]

        # New session
        if session_num == "":
 
            # an `action_listen` should be added at the end as a user message follows
            events.append(ActionExecuted("action_listen"))

        # timed out session
        else:
            dispatcher.utter_message(template="utter_timeout")
            events.append(FollowupAction('action_end_dialog'))

        return events


# When people open the chat twice in different browsers, the user name in the
# second browser may be set to the first intent the frontend sends to rasa.
# In that case we want to end the dialog.
# And we also want to check if the user name has been extracted correctly.
class ActionCheckNameslot(Action):
    def name(self) -> Text:
        return "action_check_nameslot"

    async def run(
      self, dispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        user_name = tracker.get_slot("user_name_slot")
 
        if "start_session" in user_name:
            dispatcher.utter_message(template="utter_multiple_open_chats")
            return [FollowupAction('action_end_dialog')]
 
        # For safety we want only one word for the name
        # Splits at whitespace
        # And also want to make sure there are no numbers in there
        # (some people may type their prolific ID)
        # and that people do not just type "hi" or "trial"
        if len(user_name.split()) == 1 and user_name.lower() != "hi" and user_name.lower() != "trial" and not "5" in user_name and not "6" in user_name:
            return[SlotSet("user_name_exists", True)]

        else:
            return[SlotSet("user_name_exists", False),
                   SlotSet("user_name_slot", "default")]


class ActionEndDialog(Action):
    """Action to cleanly terminate the dialog."""
    # This action just calla the default restart action
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

        # Ask to close the window
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


def check_session_not_done_before(cur, prolific_id, session_num):

    # check if there is some data already saved about this session. This happens
    # as soon as the user has already answered the dropout question for this
    # session
    if int(session_num) > 1:

        query = ("SELECT * FROM sessiondata WHERE prolific_id = %s and session_num = %s")
        cur.execute(query, [prolific_id, session_num])
        done_before_result = cur.fetchone()

    # For session 1, sessiondata is only saved at the very end of the session.
    # But we do not want people to be able to do the entire session twice.
    # So instead we check if there is already data on the person in the users table.
    # This means that the person has previously entered their name and their mood,
    # as we save the name after the mood has been entered.
    else:
        query = ("SELECT * FROM users WHERE prolific_id = %s")
        cur.execute(query, [prolific_id])
        done_before_result = cur.fetchone()

    not_done_before = True

    # user has done the session before
    if done_before_result is not None:
        not_done_before = False

    return not_done_before


class ActionLoadSessionFirst(Action):
    
    def name(self) -> Text:
        return "action_load_session_first"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        prolific_id = tracker.current_state()['sender_id']
        session_loaded = False

        try:
            conn = mysql.connector.connect(
                user=DATABASE_USER,
                password=DATABASE_PASSWORD,
                host=DATABASE_HOST,
                port=DATABASE_PORT,
                database='db'
            )
            cur = conn.cursor(buffered=True)
 
            session_loaded = check_session_not_done_before(cur, prolific_id, 1)

        except mysql.connector.Error as error:
            logging.info("Error in loading first session: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()

        return [SlotSet("session_loaded", session_loaded)]


class ActionLoadSessionNotFirst(Action):

    def name(self) -> Text:
        return "action_load_session_not_first"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        prolific_id = tracker.current_state()['sender_id']
        session_num = tracker.get_slot("session_num")
        smoker = tracker.get_slot("smoker")

        session_loaded = True
        mood_prev = ""
        activity_verb_prev = ""
        user_name_exists = False

        try:
            conn = mysql.connector.connect(
                user=DATABASE_USER,
                password=DATABASE_PASSWORD,
                host=DATABASE_HOST,
                port=DATABASE_PORT,
                database='db'
            )
            cur = conn.cursor(buffered=True)

            # get user name from database
            query = ("SELECT name FROM users WHERE prolific_id = %s")
            cur.execute(query, [prolific_id])
            user_name_result = cur.fetchone()

            if user_name_result is None:
                session_loaded = False

            else:
                user_name_result = user_name_result[0]
                # Check if the user name is not our default value (which means that
                # we could not extract the user name)
                if user_name_result != "default":
                    user_name_exists = True

                # Check if user has done previous session before '
                # (i.e., if session data is saved from previous session)
                query = ("SELECT * FROM sessiondata WHERE prolific_id = %s and session_num = %s and response_type = %s")
                cur.execute(query, [prolific_id, str(int(session_num) - 1), "state_energy"])
                done_previous_result = cur.fetchone()

                if done_previous_result is None:
                    session_loaded = False
 
                else:
                    # Check if user has not done this session before
                    # checks if some data on this session is already saved in database
                    # this basically means that it checks whether the user has already 
                    # completed the session part until the dropout question before,
                    # since that is when we first save something to the database
                    session_loaded = check_session_not_done_before(cur, prolific_id, 
                                                                   session_num)

                    logging.info("session_loaded: " + str(session_loaded))

                    if session_loaded:
                        # Get mood from previous session
                        query = ("SELECT response_value FROM sessiondata WHERE prolific_id = %s and session_num = %s and response_type = %s")
                        cur.execute(query, [prolific_id, str(int(session_num) - 1), "mood"])
                        mood_prev = cur.fetchone()[0]
                        # Get activity index from previous session
                        query = ("SELECT response_value FROM sessiondata WHERE prolific_id = %s and session_num = %s and response_type = %s")
                        cur.execute(query, [prolific_id, str(int(session_num) - 1), "activity_new_index"])
                        act_index = int(cur.fetchone()[0])
                        activity_verb_prev = df_act.iloc[act_index]["Verb"]
                        # Adapt verb formulation to vaping if needed
                        if smoker == "0":
                            activity_verb_prev = activity_verb_prev.replace("smok", "vap")
     

        except mysql.connector.Error as error:
            session_loaded = False
            user_name_result = "default"
            logging.info("Error in loading session not first: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()


        return [SlotSet("user_name_slot_not_first", user_name_result),
                SlotSet("mood_prev_session", mood_prev),
                SlotSet("session_loaded", session_loaded),
                SlotSet("activity_prev_verb", activity_verb_prev),
                SlotSet("user_name_exists", user_name_exists)]


class ActionSaveNameToDB(Action):

    def name(self) -> Text:
        return "action_save_name_to_db"

    def run(self, dispatcher: CollectingDispatcher,
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
            cur = conn.cursor(buffered=True)
            query = "INSERT INTO users(prolific_id, name, time) VALUES(%s, %s, %s)"
            queryMatch = [tracker.current_state()['sender_id'], 
                          tracker.get_slot("user_name_slot"),
                          formatted_date]
            cur.execute(query, queryMatch)
            conn.commit()

        except mysql.connector.Error as error:
            logging.info("Error in saving name to db: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()

        return []


class ActionSaveActivityExperience(Action):
    def name(self):
        return "action_save_activity_experience"

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
            cur = conn.cursor(buffered=True)

            prolific_id = tracker.current_state()['sender_id']
            session_num = tracker.get_slot("session_num")
            slots_to_save = ["effort", "activity_experience_slot",
                             "activity_experience_mod_slot",
                             "dropout_response"]
            for slot in slots_to_save:

                save_sessiondata_entry(cur, conn, prolific_id, session_num,
                                       slot, tracker.get_slot(slot),
                                       formatted_date)

        except mysql.connector.Error as error:
            logging.info("Error in saving activity experience to db: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()

        return []


def save_sessiondata_entry(cur, conn, prolific_id, session_num, response_type,
                           response_value, time):
    query = "INSERT INTO sessiondata(prolific_id, session_num, response_type, response_value, time) VALUES(%s, %s, %s, %s, %s)"
    cur.execute(query, [prolific_id, session_num, response_type,
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
            cur = conn.cursor(buffered=True)

            prolific_id = tracker.current_state()['sender_id']
            session_num = tracker.get_slot("session_num")

            slots_to_save = ["smoker", 
                             "mood", 
                             "state_importance", 
                             "state_selfefficacy", 
                             "state_humansupport", 
                             "state_energy",
                             "activity_new_index",
                             "human_support_after_session"]

            # Also need to save slot with introduction to human coach in session 1
            if session_num == "1":
                slots_to_save.append("human_coach_introduction_slot")

            for slot in slots_to_save:

                save_sessiondata_entry(cur, conn, prolific_id, session_num,
                                       slot, tracker.get_slot(slot),
                                       formatted_date)

        except mysql.connector.Error as error:
            logging.info("Error in save session: " + str(error))

        finally:
            if conn.is_connected():
                cur.close()
                conn.close()

        return []


def get_previous_activity_indices_from_db(prolific_id):
    "Get indices of the activities previously done by the user from the db."

    try:
        conn = mysql.connector.connect(
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            database='db'
        )
        cur = conn.cursor(buffered=True)

        # Get previous activity indices from db
        query = ("SELECT response_value FROM sessiondata WHERE prolific_id = %s and response_type = %s")
        cur.execute(query, [prolific_id, "activity_new_index"])
        result = cur.fetchall()

        # So far, we have sth. like [('19',), ('22',)]
        result = [i[0] for i in result]

    except mysql.connector.Error as error:
        logging.info("Error in getting previous activity indices from db: " + str(error))

    finally:
        if conn.is_connected():
            cur.close()
            conn.close()

    return result


def get_activity_counts_from_db():
    "Compute how many times each activity has already been chosen overall."

    try:
        conn = mysql.connector.connect(
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            database='db'
        )
        cur = conn.cursor(buffered=True)

        # Get activity indices from database
        query = ("SELECT response_value FROM sessiondata WHERE response_type = %s AND response_value IS NOT NULL")
        cur.execute(query, ["activity_new_index"])
        result = cur.fetchall()

        activity_indices = [int(i[0]) for i in result if not i[0] == '']
        activity_counts = [activity_indices.count(i) for i in range(0, NUM_ACTIVITIES)]

    except mysql.connector.Error as error:
        logging.info("Error in getting activity counts from db: " + str(error))

    finally:
        if conn.is_connected():
            cur.close()
            conn.close()

    return activity_counts


class ActionChooseActivity(Action):
    def name(self):
        return "action_choose_activity"

    async def run(self, dispatcher, tracker, domain):

        prolific_id = tracker.current_state()['sender_id']
        smoker = tracker.get_slot("smoker")

        # get indices of previously assigned activities
        # this returns a list of strings
        curr_act_ind_list = get_previous_activity_indices_from_db(prolific_id)

        if curr_act_ind_list is None:
            curr_act_ind_list = []

        # check excluded activities for previously assigned activities
        excluded = []
        for i in curr_act_ind_list:
            excluded += df_act.loc[int(i), 'Exclusion']

        # get eligible activities (not done before and not excluded)
        remaining_indices = [i for i in range(NUM_ACTIVITIES) if not str(i) in curr_act_ind_list and not str(i) in excluded]

        # Check if prerequisites for remaining activities are met
        for i in remaining_indices:
            # Get prerequisites that are met
            preq = [j for j in df_act.loc[i, 'Prerequisite'] if j in curr_act_ind_list]
            # Exclude activities for which there is at least one prerequisite and
            # not at least one prerequisite is met.
            if (len(df_act.loc[i, 'Prerequisite']) > 0 and len(preq) == 0):
                excluded.append(str(i))

        # Get activities that also meet the prerequisites
        remaining_indices = [i for i in remaining_indices if not str(i) in excluded]

        # Compute how often each activity has already been chosen in the past
        activity_counts = get_activity_counts_from_db()

        # Choose random new activity
        # probability to be chosen is higher if activity has been chosen less often so far
        # Activity indices start at 0
        # If the count is 0, we set the weight to 1 (i.e., same weight as a count of 1)
        new_act_index = random.choices(remaining_indices,
                                       weights = [1/activity_counts[i] if activity_counts[i] > 0 else 1 for i in remaining_indices],
                                       k = 1)[0]
        
        # Determine new activity verb
        activity_new_verb = df_act.loc[new_act_index, "Verb"]
        
        # Determine new activity formulation in the session
        activity_new_formulation_session = df_act.loc[new_act_index, 'Formulation Session']
        
        # Determine new activity formulation in the email
        activity_new_formulation_email = df_act.loc[new_act_index, 'Formulation Email']
        
        # Adapt formulations to vaping if needed
        if smoker == "0":
            activity_new_verb = activity_new_verb.replace("smok", "vap")

            activity_new_formulation_session = activity_new_formulation_session.replace("smok", "vap")
            activity_new_formulation_session = activity_new_formulation_session.replace("Smok", "Vap")
            # from smoking tracking activity
            activity_new_formulation_session = activity_new_formulation_session.replace("number of cigarettes", "number of puffs")
            activity_new_formulation_session = activity_new_formulation_session.replace("2 cigarettes", "30 puffs")
            activity_new_formulation_session = activity_new_formulation_session.replace("5 cigarettes", "75 puffs")
            # from fighting match activity
            activity_new_formulation_session = activity_new_formulation_session.replace("cigarette as two", "vape as two")
            # From previous smoking successes activity
            activity_new_formulation_session = activity_new_formulation_session.replace("Maybe you once only had one instead of two cigarettes after dinner", 
                                                                                        "Maybe you once only had 10 instead of 20 puffs after dinner")

            activity_new_formulation_email = activity_new_formulation_email.replace("smok", "vap")
            activity_new_formulation_email = activity_new_formulation_email.replace("Smok", "Vap")
            # from smoking tracking activity
            activity_new_formulation_email = activity_new_formulation_email.replace("number of cigarettes", "number of puffs")
            activity_new_formulation_email = activity_new_formulation_email.replace("2 cigarettes", "30 puffs")
            activity_new_formulation_email = activity_new_formulation_email.replace("5 cigarettes", "75 puffs")
            # from fighting match activity
            activity_new_formulation_email = activity_new_formulation_email.replace("cigarette as two", "vape as two")
            # From previous smoking successes activity
            activity_new_formulation_email = activity_new_formulation_email.replace("Maybe you once only had one instead of two cigarettes after dinner", 
                                                                                    "Maybe you once only had 10 instead of 20 puffs after dinner")

        return [SlotSet("activity_formulation_new_session", activity_new_formulation_session), 
                SlotSet("activity_formulation_new_email", activity_new_formulation_email),
                SlotSet("activity_new_index", str(new_act_index)),
                SlotSet("activity_new_verb", activity_new_verb)]
    
    
def get_previous_human_support_from_db():
    """
    Get the number of times we have chosen no human support vs. human support
    in sessions 1-4.

    Returns
    -------
    support_counts : list
        number of times we have chosen no human support, number of times we have
        chosen human support

    """

    try:
        conn = mysql.connector.connect(
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            database='db'
        )
        cur = conn.cursor(buffered=True)

        # Get human support counts in sessions 1-4 from database
        query = ("SELECT response_value FROM sessiondata WHERE response_type = %s AND response_value IS NOT NULL AND session_num != %s")
        cur.execute(query, ["human_support_after_session", "5"])
        result = cur.fetchall()

        support_values = [int(i[0]) for i in result if not i[0] == '']
        # Possible values are just 0 and 1 (i.e., no support vs. support)
        support_counts = [support_values.count(i) for i in range(0, 2)]

    except mysql.connector.Error as error:
        logging.info("Error in getting human support counts from db: " + str(error))

    finally:
        if conn.is_connected():
            cur.close()
            conn.close()
   
    return support_counts


class ActionChooseHumanSupport(Action):
    def name(self):
        return "action_choose_human_support"

    async def run(self, dispatcher, tracker, domain):
        
        session_num = float(tracker.get_slot('session_num'))  # this is a string originally
        
        # Only potentially provide human support after sessions 1-4 since we
        # do not get an RL sample starting in session 5. So human support there
        # would be wasted.
        human_support_after_session = False
        if session_num <= 4:
            #human_support_after_session = np.random.choice([False, True], size = 1, 
            #                                               p = [1-PROB_HUMAN_SUPPORT, PROB_HUMAN_SUPPORT])[0]

            # Get support counts from db
            support_counts = get_previous_human_support_from_db()
            total_entries = sum(support_counts)
            # If number of times we have given human support is less than the proportion we
            # should have at this point, then we give human support
            if support_counts[1] < total_entries * PROB_HUMAN_SUPPORT:
                human_support_after_session = True

        # Since importing numpy, we for some reason need the conversion to bool
        return [SlotSet("human_support_after_session", bool(human_support_after_session))]


# Send reminder email with activity
class ActionSendEmail(Action):
    def name(self):
        return "action_send_email"

    async def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Get user ID
        prolific_id = tracker.current_state()['sender_id']

        activity_formulation_email = tracker.get_slot('activity_formulation_new_email')
        session_num = tracker.get_slot('session_num')  # this is a string

        ssl_port = 465
        with open('x.txt', 'r') as f:
            x = f.read()
            x = x.rstrip()
        smtp = "smtp.web.de"
        with open('email.txt', 'r') as f:
            email = f.read()
            email = email.rstrip()
        user_email = prolific_id + "@email.prolific.co"

        context = ssl.create_default_context()

        # set up the SMTP server
        with smtplib.SMTP_SSL(smtp, ssl_port, context = context) as server:
            server.login(email, x)

            msg = MIMEMultipart() # create a message

            # Have a different message template for the last session
            # And also have no next session then
            template_file_name = "reminder_template_notlast.txt"
            if session_num == "5":
                template_file_name = "reminder_template_last.txt"
                activity_formulation_email = activity_formulation_email.replace(" before the next session,", "")
                activity_formulation_email = activity_formulation_email.replace(" before the next session", "")
                activity_formulation_email = activity_formulation_email.replace("Before the next session, I", "I")


            with open(template_file_name, 'r', encoding='utf-8') as template_file:
                message_template = Template(template_file.read())

            # Add the actual info to the message template
            message_text = message_template.substitute(PERSON_NAME ="Study Participant",
                                                       ACTIVITY= activity_formulation_email)

            # Set up the parameters of the message
            msg['From'] = email
            msg['To']=  user_email
            msg['Subject'] = "Activity Reminder - Peparing for Quitting"

            # Add the message body
            msg.attach(MIMEText(message_text, 'plain'))

            # Send the message via the server set up earlier.
            server.send_message(msg)

            del msg

        return []


class ValidateUserNameForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_user_name_form'

    def validate_user_name_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate user_name_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_user_name_slot':
            return {"user_name_slot": None}

        if not len(value) >= 1:
            dispatcher.utter_message(response="utter_longer_name")
            return {"user_name_slot": None}

        return {"user_name_slot": value}


class ValidateActivityExperienceForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_activity_experience_form'

    def validate_activity_experience_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate activity_experience_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_activity_experience_slot':
            return {"activity_experience_slot": None}

        # People should type a certain minimum number of characters
        if len(value) < MIN_CHAR_EXPERIENCE:
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"activity_experience_slot": None}

        return {"activity_experience_slot": value}


class ValidateActivityExperienceModForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_activity_experience_mod_form'

    def validate_activity_experience_mod_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate activity_experience_mod_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_activity_experience_mod_slot':
            return {"activity_experience_mod_slot": None}

        # People should either type "none" or say a bit more
        if not (len(value) >= MIN_CHAR_EXPERIENCE_MOD or "none" in value.lower()):
            dispatcher.utter_message(response="utter_provide_more_detail")
            return {"activity_experience_mod_slot": None}

        return {"activity_experience_mod_slot": value}


class ValidateHumanCoachIntroductionForm(FormValidationAction):
    def name(self) -> Text:
        return 'validate_human_coach_introduction_form'

    def validate_human_coach_introduction_slot(
            self, value: Text, dispatcher: CollectingDispatcher,
            tracker: Tracker, domain: Dict[Text, Any]) -> Dict[Text, Any]:
        # pylint: disable=unused-argument
        """Validate human_coach_introduction_slot input."""
        last_utterance = get_latest_bot_utterance(tracker.events)

        if last_utterance != 'utter_ask_human_coach_introduction_slot' :
            return {"human_coach_introduction_slot": None}

        # People should type a certain minimum number of characters
        if len(value) < MIN_CHAR_HUMAN_COACH_INTRO:
            dispatcher.utter_message(response="utter_provide_more_detail_human_coach_intro")
            return {"human_coach_introduction_slot": None}

        return {"human_coach_introduction_slot": value}
