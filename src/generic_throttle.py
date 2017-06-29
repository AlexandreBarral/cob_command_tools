#!/usr/bin/python

import rospy
import roslib
import rostopic
from threading import Lock
from functools import partial


class GenericThrottle:
    def __init__(self):
        self.namespace = None
        self.topic_dictionary = None
        self.topic_framerate = None
        self.delay = None
        self._node_handle = rospy.init_node('generic_throttle')

        # Read /generic_throttle/* parameters from server
        parameter_list = ['namespace', 'topic_framerate', 'delay']
        for parameter_name in parameter_list:
            parameter_string = '/generic_throttle/' + parameter_name
            if rospy.has_param(parameter_string):
                parameter = rospy.get_param(parameter_string)
                setattr(self,parameter_name, parameter)
            else:
                rospy.logerr('Parameter ' + parameter_string + ' not available')
                exit(5)

        # Check if each entry of topic_framerate has 2 entries
        size_flag = all(len(item) == 2 for item in self.topic_framerate)

        if(not(size_flag)):
            rospy.logerr('Parameter /generic_throttle/framerate must be'
                         ' a list of size 2 lists')
            exit(10)

        self._populate_dictionary()
        rospy.spin()

    def timer_callback(self, event, topic_id):

        locking = self.topic_dictionary[topic_id]['lock'].acquire_lock(False)
        # The False argument is for a non blocking call

        if not(locking):
            rospy.logwarn('Cannot lock topic ' + topic_id)
            return

        publisher = self.topic_dictionary[topic_id]['publisher']
        subscriber = self.topic_dictionary[topic_id]['subscriber']

        # Check if pub and sub already exist, if not try to create them after
        # checking the rostopic

        if None in(publisher, subscriber):
            topic_info = rostopic.get_topic_class(topic_id)
            if topic_info[0] is None:
                rospy.logwarn('Cannot find topic ' + topic_id)

                self.topic_dictionary[topic_id]['lock'].release_lock()
                return
            else:
                # Create publisher
                self.topic_dictionary[topic_id]['publisher'] = \
                    rospy.Publisher(self.namespace + topic_id, topic_info[0],
                                    queue_size=10)
                rospy.loginfo('Created publisher for ' + self.namespace +
                              topic_id)
                # Create subscriber
                subscriber_partial = partial(self.subscriber_callback,
                                             topic_id=topic_id)
                self.topic_dictionary[topic_id]['subscriber'] = \
                    rospy.Subscriber(topic_id, topic_info[0],
                                     subscriber_partial)
                rospy.loginfo('Created subscriber for ' + topic_id)

                self.topic_dictionary[topic_id]['lock'].release_lock()
                return

        last_message = self.topic_dictionary[topic_id]['last_message']
        if last_message is None:
            rospy.logwarn('No message available for ' + topic_id + ' yet')
            self.topic_dictionary[topic_id]['lock'].release_lock()
            return
        else:
            last_timestamp = self.topic_dictionary[topic_id]['last_timestamp']
            if rospy.Time.now() - last_timestamp > rospy.Duration(self.delay):
                rospy.logwarn('Last message older than ' + str(self.delay.secs)
                              +' s. Discard last message')
                self.topic_dictionary[topic_id]['last_message'] = None
                self.topic_dictionary[topic_id]['lock'].release_lock()
                return
            else:
                self.topic_dictionary[topic_id]['publisher'].publish(
                    last_message)
                self.topic_dictionary[topic_id]['lock'].release_lock()
                return

    def subscriber_callback(self, data, topic_id):
        locking = self.topic_dictionary[topic_id]['lock'].acquire_lock(False)
        # The False argument is for a non blocking call

        if not (locking):
            rospy.logwarn('Cannot lock topic ' + topic_id)
            return

        if data._has_header:
            self.topic_dictionary[topic_id]['last_timestamp'] = \
                data.header.stamp
        else:
            self.topic_dictionary[topic_id]['last_timestamp'] = \
                rospy.Time.now()

        self.topic_dictionary[topic_id]['last_message'] = data
        self.topic_dictionary[topic_id]['lock'].release_lock()

    def _populate_dictionary(self):
        # Topic dictionary structure
        # {topic_name: {framerate, timer, last_message,
        # subscriber, publisher, lock}
        self.topic_dictionary = {key: {'framerate': value, 'timer': None,
                                       'last_message': None,
                                       'last_timestamp': None,
                                       'subscriber': None,
                                       'publisher': None, 'lock': None}
                                 for (key, value) in self.topic_framerate}

        for key, element in self.topic_dictionary.iteritems():
            # Create Timer for each topic
            personal_callback = partial(self.timer_callback, topic_id=key)
            element['timer'] = rospy.Timer(
                rospy.Duration(1. / element['framerate']),
                personal_callback)
            # Create Lock for each topic
            element['lock'] = Lock()