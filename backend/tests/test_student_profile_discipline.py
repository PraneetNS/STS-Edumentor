import unittest
from agent.student_profile import StudentProfileManager
from agent.models import Emotion

class TestStudentProfileDiscipline(unittest.TestCase):
    def setUp(self):
        # Initialize a new manager using an in-memory or custom temporary path
        # Let's mock a profile state for testing
        self.manager = StudentProfileManager()
        # Reset defaults
        self.manager._profile.discipline = "cse"
        self.manager._profile.active_topics = []

    def test_get_discipline_default(self):
        self.assertEqual(self.manager.get_discipline(), "cse")

    def test_dynamic_discipline_update_on_topic_match(self):
        # Update profile when user talks about Civil Engineering
        self.manager.update_from_turn(
            user_text="let's study concrete columns and beams structural design RCC RCC RCC",
            assistant_text="Sure, civil concrete structures are fun.",
            emotion=Emotion.NEUTRAL
        )
        self.assertEqual(self.manager.get_discipline(), "civil")
        self.assertIn("Civil Engineering", self.manager._profile.active_topics)

    def test_dynamic_discipline_aerospace_match(self):
        # Update profile when user talks about Aerospace Engineering
        self.manager.update_from_turn(
            user_text="how does wing aerodynamics lift coefficient and thrust work?",
            assistant_text="Lift and thrust are key aerospace mechanics.",
            emotion=Emotion.NEUTRAL
        )
        self.assertEqual(self.manager.get_discipline(), "aerospace")
        self.assertIn("Aerospace Engineering", self.manager._profile.active_topics)

if __name__ == '__main__':
    unittest.main()
