import unittest
from agent.student_profile import StudentProfileManager
from agent.models import Emotion

class TestStudentProfileDiscipline(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Initialize a new manager using default config
        self.manager = StudentProfileManager()
        # Reset defaults
        self.manager._profile.discipline = "cse"
        self.manager._profile.active_topics = []

    async def test_get_discipline_default(self):
        disc = await self.manager.get_discipline()
        self.assertEqual(disc, "cse")

    async def test_dynamic_discipline_update_on_topic_match(self):
        # Update profile when user talks about Civil Engineering
        await self.manager.update_from_turn(
            user_text="let's study concrete columns and beams structural design RCC RCC RCC",
            assistant_text="Sure, civil concrete structures are fun.",
            emotion=Emotion.NEUTRAL
        )
        disc = await self.manager.get_discipline()
        self.assertEqual(disc, "civil")
        self.assertIn("Civil Engineering", self.manager._profile.active_topics)

    async def test_dynamic_discipline_aerospace_match(self):
        # Update profile when user talks about Aerospace Engineering
        await self.manager.update_from_turn(
            user_text="how does wing aerodynamics lift coefficient and thrust work?",
            assistant_text="Lift and thrust are key aerospace mechanics.",
            emotion=Emotion.NEUTRAL
        )
        disc = await self.manager.get_discipline()
        self.assertEqual(disc, "aerospace")
        self.assertIn("Aerospace Engineering", self.manager._profile.active_topics)

if __name__ == '__main__':
    unittest.main()
