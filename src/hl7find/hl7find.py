#!/usr/bin/env python

from functools import reduce
import re

class InvalidHL7FindSyntaxException(Exception):
    def __init__(self,extra_message):
        self.message = f"Invalid HL7 Find Syntax {extra_message}"
        super().__init__(self. message)

class HL7AmbiguousSegmentException(Exception):
    def __init__(self, message):
        super().__init__("Ambiguous segment selection: " + message)

class HL7PicketFenceException(Exception):
    "HL7 Index Notation starts at 1 given 0"
    pass

class HL7UpdateAttemptTooDeep(Exception):
    def __init__(self, search_string):
        super().__init__(f"Attempt to set value at too deep a position given: {search_string}")

class HL7Message:
    def __init__(self,message_string, **kwargs):
        self._options = dict(kwargs,**{'raise_on_ambiguous': True})
        self._parsing_elements = list(message_string[3:8])
        self._escape = self._parsing_elements[3]
        self._repeating = self._parsing_elements[2]
        self._delimeters = [self._parsing_elements[0],self._parsing_elements[1],self._parsing_elements[4]]
        self._segments = message_string.splitlines()
        self._internal_structure = list(map(lambda seg: (seg[:3], self._parse(seg,self._delimeters)[1:]), self._segments))
        # fix MSH.1 with values for field separator otherwise parsing turns it into a repeating field with wonky values
        fixed_msh = self._internal_structure[0][1][1:]
        fixed_msh.insert(0,f"{self._delimeters[1]}{self._repeating}{self._escape}{self._delimeters[2]}")
        self._internal_structure[0] = (self._internal_structure[0][0], fixed_msh)


    # Segment splitting is handled above
    # This handles splitting based on the delimeters specified
    # in the MSH segment into lists and the grouping of repeating
    # fields into tuples.
    # Using tuples to distinguish repeating fields is vital for
    # the wildcare find syntax used below (e.g. ZF1.4*.1 which returns
    # the first sub element of the ZF1.4 repeating field)
    def _parse(self,part,given_delimeters):
        dels = given_delimeters.copy()
        if len(given_delimeters) == 0:
            return part
        else:
            current_del = dels.pop(0) #dels now the rest
            n_parts = part.split(current_del)
            # Assumes there will always be at least one delimerter at the top level (which meets the spec)
            if len(n_parts) == 1 and len(given_delimeters) < 3: # Not the first delimeter
                return self._repeat_split(part)
            elif len(given_delimeters) < 3:
                # look for repeating fields before splitting
                repititions = self._repeat_split(part)
                if type(repititions) is tuple:
                    return tuple(map(lambda rep: list(map(lambda p: self._parse(p,dels), rep.split(current_del))), repititions))
                else:
                    return list(map(lambda p: self._parse(p,dels), n_parts))
            else:
                return list(map(lambda p: self._parse(p,dels), n_parts))

    def _repeat_split(self,part):
        repititions = part.split(self._repeating)
        if len(repititions) > 1:
            return tuple(repititions)
        else:
            return part

    def segments(self):
        return self._segments

    def delimeters(self):
        return self._delimeters

    def internal_structure(self):
        return self._internal_structure

    def to_string(self, newline_char='\n'):
        def list_to_string(hl7list,delimeters):
            if type(hl7list) is tuple:
                return self._repeating.join(map(lambda repeating_item: list_to_string(repeating_item,delimeters.copy()), hl7list))
            elif type(hl7list) is list and len(delimeters) > 0:
                first_delimeter = delimeters[0]
                rest_delimeters = delimeters[1:]
                return first_delimeter.join(map(lambda item: item if type(item) not in [tuple,list] else list_to_string(item,rest_delimeters), hl7list))
            else:
                return hl7list

        return newline_char.join(map(lambda seg_tuple: f"{seg_tuple[0]}{self._delimeters[0]}{list_to_string(seg_tuple[1],self._delimeters)}",
                                     self._internal_structure))

    def find(self,search_string):
        # Add a format/syntax check here
        if not self._check_search_syntax(search_string):
            raise InvalidHL7FindSyntaxException(f"given: {search_string}")

        # Preventing duplication of [1:] token traversal
        def token_search(position, tokenized_search):
            for token in tokenized_search:
                position = self._find_with_int(position,token)
            return position

        # Handle segment selection differently because of the
        # (segment name, list) setup in self._internal_structure
        tokenized_search = search_string.split(".")
        segment_token = tokenized_search.pop(0)
        (_,position) = self._find_segment(segment_token)

        # special case repeat segment handling
        if type(position) == tuple:
            position = map(lambda seg: token_search(seg, tokenized_search), position)
        else:
            position = token_search(position, tokenized_search)

        # Forcing evaluation just in case
        if type(position) in [map, filter, reduce]:
            return list(position)
        else:
            return position

    # The primary difference in these finds is segments is a tuple
    # and the search string is alphanumeric instead of a number
    # opportunities for refactoring abound
    def _find_segment(self,token):
        if token[-1] == '*':
            indexes = [i for i,seg in filter(lambda i_seg: i_seg[1][0] == token[:-1], enumerate(self._internal_structure))]
            return (indexes,tuple(map(lambda seg: seg[1], filter(lambda seg: seg[0] == token[:-1], self._internal_structure))))
        elif token[-1] == ']':
            match = re.match(r"^([A-Z]{3})\[(\d+)\]$",token)
            seg_value = match.groups()[0]
            index = self._hl7_index_to_index(int(match.groups()[1]))
            seg_index = [i for i,seg in filter(lambda i_seg: i_seg[1][0] == seg_value, enumerate(self._internal_structure))][index]
            segment = list(filter(lambda seg: seg[0] == seg_value, self._internal_structure))[index][1]
            return (seg_index, segment)
        else:
            segments = list(filter(lambda seg: seg[0] == token, self._internal_structure))
            if len(segments) > 1 and self._options.get('raise_on_ambiguous'):
                raise HL7AmbiguousSegmentException(f"There is more than one {token} segment")
            else:
                index = [i for i,seg in filter(lambda i_seg: i_seg[1][0] == token, enumerate(self._internal_structure))]
                return (index[0],segments[0][1])

    def _find_with_int(self,position, token):
        if type(position) == tuple: # Return of a repeating set
            return tuple(map(lambda p: self._find_with_int(p,token), position))
        if token[-1] == ']':
            match = re.match(r"^(\d+)\[(\d+)\]$",token)
            seg_index = self._hl7_index_to_index(int(match.groups()[0]))
            repeating_index = self._hl7_index_to_index(int(match.groups()[1]))
            # Could run check to see if postion[seg_index] is a tuple and raise accordingly
            return list(position)[seg_index][repeating_index]
        elif token[-1] == '*':
            index = self._hl7_index_to_index(int(token[:-1]))
            seg = position[index]
            return tuple(seg)
        else:
            #index = int(token[:-1]) if token[-1] == '*' else int(token)
            index = self._hl7_index_to_index(int(token))
            seg = position[index]
            if type(seg) in [tuple] and self._options.get('raise_on_ambiguous') and token[-1] != '*':
                raise HL7AmbiguousSegmentException(f"There is more than one value for segment {token} in {position}")
            else:
                return seg

    def _hl7_index_to_index(self,given_int):
        if given_int == 0:
            raise HL7PicketFenceException()
        elif given_int < 0:
            return given_int
        else:
            return given_int - 1

    def _check_search_syntax(self,search_string):
        def is_or_with_selector(is_test, tokens):
            return (is_test(tokens[0])
                    and (len(tokens) == 1
                         or
                         tokens[1] == ''
                         or
                         re.match(r"^\d+\]$",tokens[1]) != None))

        tokens = list(map(lambda t: re.split(r"\*|\[", t), search_string.split(".")))
        valid = True if is_or_with_selector(lambda t: re.match(r"^\w{3}$", t) != None, tokens[0]) else False
        for token in tokens[1:]:
            if not is_or_with_selector(lambda t: re.match(r"^-*\d+$", t), token):
                valid = False
                break
        return valid

    def copy(self):
        return HL7Message(self.to_string())

    def add_segment(self,seg,value,index=None):
        if index and type(index) is int: # also filters out 0 which would override MSH
            head = self._internal_structure[:index+1]
            tail = self._internal_structure[index:]
            head[index] = (seg, value)
            head.extend(tail)
            self._internal_structure = head
        else:
            self._internal_structure.append((seg,value))


    def update(self,search_string,value):
        if re.match(r"^\w{3}(\[-?\d+\])?(\.-?\d+){0,3}$", search_string) == None:
            raise InvalidHL7FindSyntaxException("update search string must refer to only one location")

        tokenized_search = search_string.split(".")
        segment_token = tokenized_search[0]
        if len(tokenized_search) == 1: # Just the segment being updated
            index, seg = self._find_segment(segment_token)
            intstruc = list(self._internal_structure)
            new_seg = list(intstruc[index])
            intstruc[index] = (new_seg[0],value)
            self._internal_structure = intstruc
        else: # Any other depth updated
            indexes = list(map(lambda s: self._hl7_index_to_index(int(s)), tokenized_search[1:]))
            rindexes = indexes.copy()
            rindexes.reverse() # the lack of functional paradigms kills me
            (_, position) = self._find_segment(segment_token)
            previous_position = None

            while len(rindexes) > 0:
                index = rindexes.pop()
                print(f"In the while with:\nindex: {index}\nindexes: {rindexes}")
                # Extend any list that's too short and
                # raise if the position given is not a list
                if type(position) is list and len(position) < (index + 1):
                    diff = (index + 1) - len(position)
                    position.extend(list(map(lambda x: [], range(diff))))
                    previous_position = position
                    position = position[index]
                elif type(position) is list:
                    previous_position = position
                    position = position[index]
                else:
                    raise HL7UpdateAttemptTooDeep(search_string)

            # Previous position is used in order to set the internal
            # structure correctly otherwise it's just changing the value
            # of the leaf which doesn't change the internal structure
            # we want mutation. A copy method is available for those that
            # want to keep the original message intact akin to other python
            # data structures.
            previous_position[indexes[-1]] = value
            return previous_position



if __name__ == '__main__':
    pass
