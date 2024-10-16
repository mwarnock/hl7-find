#!/usr/bin/env python

import unittest, hl7find

class TestHL7Message(unittest.TestCase):

    def setUp(self):
        f = open('tests/sample-oru.hl7')
        hl7_s = f.read()
        f.close()
        self.hl7_string = hl7_s
        self.msg = hl7find.HL7Message(self.hl7_string)


    def test_parse(self):
        self.assertEqual(type(self.msg.internal_structure()),list)
        self.assertEqual(len(self.msg.internal_structure()),20)
        self.assertTrue('MSH' in map(lambda t: t[0], self.msg.internal_structure()))

    def test_shallow_simple_find(self):
        self.assertEqual(self.msg.find("MSH.2"),"SendingApp")
        self.assertEqual(self.msg.find("PID.3.4.3"),"ISO")

    def test_negative_index(self):
        self.assertEqual(self.msg.find("PID.3.-1"),"MR")

    def test_repeating_segment(self):
        self.assertEqual(len(self.msg.find("OBX*")),14)
        self.assertEqual(self.msg.find("OBX[1].1"), '1')
        with self.assertRaises(hl7find.HL7AmbiguousSegmentException):
            self.msg.find("OBX.1")
        self.assertEqual(self.msg.find("OBX*.1")[0],'1')
        self.assertEqual(self.msg.find("OBX*.3.1")[0],'wbc')
        self.assertEqual(self.msg.find("OBX*.3.1")[1],'neutros')

    def test_repeating_field(self):
        self.assertEqual(self.msg.find("ZF1.1"),'TEST')
        self.assertEqual(self.msg.find("ZF1.-2"),'z end')
        with self.assertRaises(hl7find.HL7AmbiguousSegmentException):
            self.msg.find("ZF1.2")
        self.assertEqual(self.msg.find("ZF1.2*"),('REPEAT 1','REPEAT 2','REPEAT 3'))
        self.assertEqual(self.msg.find("ZF1.2*.1"),('R','R','R'));
        self.assertEqual(self.msg.find("ZF1.2[2]"),('REPEAT 2'));

    def test_repeating_segment_and_field(self):
        self.assertEqual(self.msg.find("ZF1.4*.1"),('deeper','deeper'))
        self.assertEqual(self.msg.find("ZF1.4*.3"),('1','2'))

    def test_bad_syntax(self):
        self.assertFalse(self.msg._check_search_syntax("OBX^.2"))
        self.assertFalse(self.msg._check_search_syntax("1.2"))
        self.assertTrue(self.msg._check_search_syntax("OBX.2"))
        self.assertTrue(self.msg._check_search_syntax("OBX*"))
        self.assertTrue(self.msg._check_search_syntax("OBX*.2"))
        self.assertTrue(self.msg._check_search_syntax("PID.-1"))
        self.assertTrue(self.msg._check_search_syntax("ZF1.2*.3"))
        with self.assertRaises(hl7find.InvalidHL7FindSyntaxException):
            self.msg.find("badsyntax")

    def test_emit(self):
        self.assertEqual(self.hl7_string, self.msg.to_string())

    def test_copy(self):
        self.assertEqual(self.msg.copy().to_string(), self.msg.to_string())

    # These tests mutate msg, but it's setup fresh for each test function
    def test_segment_update(self):
        self.msg.update("ZF1",['test','a','value',['a','sub','value'],('and','a','repeating','field')])
        self.assertEqual(self.msg.find("ZF1.1"),'test')
        self.assertEqual(self.msg.find("ZF1.4.2"),'sub')
        self.assertEqual(self.msg.find("ZF1.5[3]"),'repeating')

        # self.msg.update("PID.2"["567","John","Doe"])
        # self.assertEqual(self.msg.find("PID.2.2"),"John")

    def test_basic_update(self):
        self.msg.update("MSH.2","New Sending Facility")
        self.assertEqual(self.msg.find("MSH.2"),"New Sending Facility")

        self.msg.update("PID.3.4.1","Pants")
        self.assertEqual(self.msg.find("PID.3.4.1"),"Pants")

        self.msg.update("MSH.-1","end")
        self.assertEqual(self.msg.find("MSH.-1"),"end")

        self.msg.update("MSH.100","added elements automatically")
        self.assertEqual(self.msg.find("MSH.100"),"added elements automatically")

        self.msg.update("PID.3.12","added elements")
        self.assertEqual(self.msg.find("PID.3.12"),"added elements")


    def test_indexed_segment_update(self):
        self.msg.update("OBX[2].1","100")
        self.assertEqual(self.msg.find("OBX[2].1"),"100")

    def test_exceptions_on_update(self):
        with self.assertRaises(hl7find.HL7UpdateAttemptTooDeep):
            self.msg.update("MSH.2.1","test")
        with self.assertRaises(hl7find.InvalidHL7FindSyntaxException):
            self.msg.update("OBX*.1","test")

if __name__ == '__main__':
    unittest.main()
