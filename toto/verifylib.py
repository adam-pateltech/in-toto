"""
<Program Name>
  verifylib.py

<Author>
  Lukas Puehringer <lukas.puehringer@nyu.edu>

<Started>
  June 28, 2016

<Copyright>
  See LICENSE for licensing information.

<Purpose>

Verification:
    1. Load root layout
      - Search for one of
        - passed layout name, or
        - 'root.layout' in current directory
        - in a bundle?

      - Check if properly formatted
    2. Load root key
      - by passed name
    3. Check signature of layout
    4. For each step in layout
      - Load link and add to link list
      - Check if poprerly formatted
    5. For each inspection
      - Execute with toto-run and add to link list

    6. For each link in link list
      - Check signature
      - Check matchrule
      - Check command

"""
import sys

import toto.util
import toto.runlib
import toto.models.layout
import toto.models.link
import toto.models.matchrule
import toto.ssl_crypto.keys
import toto.log as log

def toto_verify(layout_path, layout_key):

  # Load layout (validates format)
  try:
    log.doing("'%s' - load layout" % layout_path)
    layout = toto.models.layout.Layout.read_from_file(layout_path)
  except Exception, e:
    log.error("in load layout - %s" % e)
    sys.exit(1) # XXX LP: re-raise?

  try:
    log.doing("'%s' - load key '%s'" % (layout_path, layout_key))
    # XXX LP: Change key load
    layout_key_dict = toto.util.create_and_persist_or_load_key(layout_key)
  except Exception, e:
    log.error("in load key - %s" % e)

  # Verify signature
  try:
    log.doing("'%s' - verify signature - key '%s'" \
        % (layout_path, layout_key))

    msg = "'%s' - verify signature" % layout_path
    if layout.verify_signature(layout_key_dict):
      log.passing(msg)
    else:
      log.failing(msg)

  except Exception, e:
    log.error("in verify signature - %s" % e)

    raise # XXX LP: exit gracefully instead of exception?

  step_links = {}

  # Load links by steps
  for step in layout.steps:
    try:
      step_name = "%s.link" % step.name
      log.doing("'%s' - '%s' - load link" % (layout_path, step.name))
      link = toto.models.link.Link.read_from_file(step_name)
    except Exception, e:
      log.error("in load link - %s" % e)
      continue
    else:
      step_links[step.name] = link

    # Fetching keys from layout
    keys = []
    for keyid in step.pubkeys:
      try:
        log.doing("'%s' - '%s' - fetch key '%s'" \
            % (layout_path, step.name, keyid))
        key = layout.keys.get(keyid)
      except Exception, e:
        log.error("in fetch key - %s" % e)
        continue
      else:
        keys.append(key)


    # Verify signature of each link file
    for key in keys:
      try:
        log.doing("'%s' - '%s' - verify signature - key '%s'" \
            % (layout_path, step.name, key["keyid"]))
        msg = "'%s' - '%s' - verify signature" % (layout_path, step.name)
        if link.verify_signature(key):
          log.passing(msg)
        else:
          log.failing(msg)
      except Exception, e:
        log.error("in verify signature - %s" % e)

    # Check expected command
    try:

      # XXX LP: We have to know for sure if both are lists or not!!
      # Then we can validate and convert (if necessary) this in the model
      expected_cmd = step.expected_command.split()
      ran_cmd = link.ran_command

      log.doing("'%s' - '%s' - align commands '%s' and '%s'" \
          % (layout_path, step.name, expected_cmd, ran_cmd))

      expected_cmd_cnt = len(expected_cmd)
      ran_cmd_cnt = len(ran_cmd)

      same_cmd_len = (expected_cmd_cnt == ran_cmd_cnt)

      msg = "'%s' - '%s' - align commands" \
          % (layout_path, step.name)

      for i in range(min(expected_cmd_cnt, ran_cmd_cnt)):
        if expected_cmd[i] != ran_cmd[i]:
          log.failing(msg)
      else:
        if same_cmd_len:
          log.passing(msg)
        else:
          log.passing("%s (with different command lengths)" % msg)

    except Exception, e:
      log.error("in align commands - %s" % e)

  inspect_links = {}
  # Execute inspections and generate link metadata
  for inspection in layout.inspect:
    try:
      log.doing("'%s' - '%s' - execute '%s'" \
          % (layout_path, inspection.name, inspection.run))

      # XXX LP: What should we record as material/product?
      # Is the current directory a sensible default? In general?
      # If so, we should propably make it a default in run_link
      # We could use matchrule paths

      # XXX LP: Is inspect.run a string or a list?
      # The specs says string, the code needs a list? Maybe split
      # the string in toto_run
      link = toto.runlib.run_link(inspection.name, ".", ".",
          inspection.run.split())

    except Exception, e:
      log.error("in run - %s" % e)
    else:
      inspect_links[inspection.name] = link


  def _verify_rules(rules, source_type, item_name, item_link, step_links):
    """ Iterates over list of rules and calls verify on them. """
    for rule_data in rules:
      try:
        rule = toto.models.matchrule.Matchrule.read(rule_data)
        rule.source_type = source_type
        log.doing("'%s' - '%s' - verify %s matchrule - %s" \
            % (layout_path, item_name, source_type, rule_data))
        rule.verify_rule(item_link, step_links)

      except toto.models.matchrule.RuleVerficationFailed, e:
        log.failing("'%s' - '%s' - verify %s matchrule - %s" \
            % (layout_path, item_name, source_type, e))
      except Exception, e:
        log.error("in verify matchrule - %s" % e)
      else:
        log.passing("'%s' - '%s' - verify %s matchrule" \
            % (layout_path, item_name, source_type))



  for item in layout.steps:
    item_link = step_links[item.name]
    _verify_rules(item.material_matchrules, "material", 
        item.name, item_link, step_links)
    _verify_rules(item.product_matchrules, "product", 
        item.name, item_link, step_links)

  for item in layout.inspect:
    item_link = inspect_links[item.name]
    _verify_rules(item.material_matchrules, "material", 
        item.name, item_link, step_links)
    _verify_rules(item.product_matchrules, "product", 
        item.name, item_link, step_links)

