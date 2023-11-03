my_model_sql = """
SELECT
a+b as c,
concat(string_a, string_b) as string_c,
not_testing, date_a,
{{ dbt.string_literal(type_numeric()) }} as macro_call,
{{ dbt.string_literal(var('my_test')) }} as var_call,
{{ dbt.string_literal(env_var('MY_TEST', 'default')) }} as env_var_call,
{{ dbt.string_literal(invocation_id) }} as invocation_id
FROM {{ ref('my_model_a')}} my_model_a
JOIN {{ ref('my_model_b' )}} my_model_b
ON my_model_a.id = my_model_b.id
"""

my_model_a_sql = """
SELECT
1 as a,
1 as id,
2 as not_testing,
'a' as string_a,
DATE '2020-01-02' as date_a
"""

my_model_b_sql = """
SELECT
2 as b,
1 as id,
2 as c,
'b' as string_b
"""

test_my_model_yml = """
unit_tests:
  - name: test_my_model
    model: my_model
    given:
      - input: ref('my_model_a')
        rows:
          - {id: 1, a: 1}
      - input: ref('my_model_b')
        rows:
          - {id: 1, b: 2}
          - {id: 2, b: 2}
    expect:
      rows:
        - {c: 2}

  - name: test_my_model_empty
    model: my_model
    given:
      - input: ref('my_model_a')
        rows: []
      - input: ref('my_model_b')
        rows:
          - {id: 1, b: 2}
          - {id: 2, b: 2}
    expect:
      rows: []

  - name: test_my_model_overrides
    model: my_model
    given:
      - input: ref('my_model_a')
        rows:
          - {id: 1, a: 1}
      - input: ref('my_model_b')
        rows:
          - {id: 1, b: 2}
          - {id: 2, b: 2}
    overrides:
      macros:
        type_numeric: override
        invocation_id: 123
      vars:
        my_test: var_override
      env_vars:
        MY_TEST: env_var_override
    expect:
      rows:
        - {macro_call: override, var_call: var_override, env_var_call: env_var_override, invocation_id: 123}

  - name: test_my_model_string_concat
    model: my_model
    given:
      - input: ref('my_model_a')
        rows:
          - {id: 1, string_a: a}
      - input: ref('my_model_b')
        rows:
          - {id: 1, string_b: b}
    expect:
      rows:
        - {string_c: ab}
    config:
        tags: test_this
"""

datetime_test = """
  - name: test_my_model_datetime
    model: my_model
    given:
      - input: ref('my_model_a')
        rows:
          - {id: 1, date_a: "2020-01-01"}
      - input: ref('my_model_b')
        rows:
          - {id: 1}
    expect:
      rows:
        - {date_a: "2020-01-01"}
"""
event_sql = """
select DATE '2020-01-01' as event_time, 1 as event
union all
select DATE '2020-01-02' as event_time, 2 as event
union all
select DATE '2020-01-03' as event_time, 3 as event
"""

datetime_test_invalid_format = """
  - name: test_my_model_datetime
    model: my_model
    given:
      - input: ref('my_model_a')
        format: xxxx
        rows:
          - {id: 1, date_a: "2020-01-01"}
      - input: ref('my_model_b')
        rows:
          - {id: 1}
    expect:
      rows:
        - {date_a: "2020-01-01"}
"""

datetime_test_invalid_format2 = """
  - name: test_my_model_datetime
    model: my_model
    given:
      - input: ref('my_model_a')
        format: csv
        rows:
          - {id: 1, date_a: "2020-01-01"}
      - input: ref('my_model_b')
        rows:
          - {id: 1}
    expect:
      rows:
        - {date_a: "2020-01-01"}
"""

event_sql = """
select DATE '2020-01-01' as event_time, 1 as event
union all
select DATE '2020-01-02' as event_time, 2 as event
union all
select DATE '2020-01-03' as event_time, 3 as event
"""

my_incremental_model_sql = """
{{
    config(
        materialized='incremental'
    )
}}

select * from {{ ref('events') }}
{% if is_incremental() %}
where event_time > (select max(event_time) from {{ this }})
{% endif %}
"""

test_my_model_incremental_yml = """
unit_tests:
  - name: incremental_false
    model: my_incremental_model
    overrides:
      macros:
        is_incremental: false
    given:
      - input: ref('events')
        rows:
          - {event_time: "2020-01-01", event: 1}
    expect:
      rows:
        - {event_time: "2020-01-01", event: 1}
  - name: incremental_true
    model: my_incremental_model
    overrides:
      macros:
        is_incremental: true
    given:
      - input: ref('events')
        rows:
          - {event_time: "2020-01-01", event: 1}
          - {event_time: "2020-01-02", event: 2}
          - {event_time: "2020-01-03", event: 3}
      - input: this
        rows:
          - {event_time: "2020-01-01", event: 1}
    expect:
      rows:
        - {event_time: "2020-01-02", event: 2}
        - {event_time: "2020-01-03", event: 3}
"""

# -- inline csv tests

test_my_model_csv_yml = """
unit_tests:
  - name: test_my_model
    model: my_model
    given:
      - input: ref('my_model_a')
        format: csv
        rows: |
          id,a
          1,1
      - input: ref('my_model_b')
        format: csv
        rows: |
          id,b
          1,2
          2,2
    expect:
      format: csv
      rows: |
        c
        2

  - name: test_my_model_empty
    model: my_model
    given:
      - input: ref('my_model_a')
        rows: []
      - input: ref('my_model_b')
        format: csv
        rows: |
          id,b
          1,2
          2,2
    expect:
      rows: []
  - name: test_my_model_overrides
    model: my_model
    given:
      - input: ref('my_model_a')
        format: csv
        rows: |
          id,a
          1,1
      - input: ref('my_model_b')
        format: csv
        rows: |
          id,b
          1,2
          2,2
    overrides:
      macros:
        type_numeric: override
        invocation_id: 123
      vars:
        my_test: var_override
      env_vars:
        MY_TEST: env_var_override
    expect:
      rows:
        - {macro_call: override, var_call: var_override, env_var_call: env_var_override, invocation_id: 123}
  - name: test_my_model_string_concat
    model: my_model
    given:
      - input: ref('my_model_a')
        format: csv
        rows: |
          id,string_a
          1,a
      - input: ref('my_model_b')
        format: csv
        rows: |
          id,string_b
          1,b
    expect:
      format: csv
      rows: |
        string_c
        ab
    config:
        tags: test_this
"""

# -- csv file tests
test_my_model_file_csv_yml = """
unit:
  - model: my_model
    tests:
      - name: test_my_model
        given:
          - input: ref('my_model_a')
            format: csv
            rows: |
              id,a
              1,1
          - input: ref('my_model_b')
            format: csv
            rows: test_my_model_fixture
        expect:
          format: csv
          rows: |
            c
            2

      - name: test_my_model_empty
        given:
          - input: ref('my_model_a')
            rows: []
          - input: ref('my_model_b')
            format: csv_file
            rows: test_my_model_fixture
        expect:
          rows: []
      - name: test_my_model_overrides
        given:
          - input: ref('my_model_a')
            format: csv_file
            rows: |
              id,a
              1,1
          - input: ref('my_model_b')
            format: csv_file
            rows: test_my_model_fixture
        overrides:
          macros:
            type_numeric: override
            invocation_id: 123
          vars:
            my_test: var_override
          env_vars:
            MY_TEST: env_var_override
        expect:
          rows:
            - {macro_call: override, var_call: var_override, env_var_call: env_var_override, invocation_id: 123}
      - name: test_my_model_string_concat
        given:
          - input: ref('my_model_a')
            format: csv_file
            rows: test_my_model_a_fixture
          - input: ref('my_model_b')
            format: csv_file
            rows: test_my_model_b_fixture
        expect:
          format: csv
          rows: |
            string_c
            ab
        config:
           tags: test_this
"""

test_my_model_fixture_csv = """
id,b
1,2
2,2
"""

test_my_model_a_fixture_csv = """
id,string_a
1,a
"""

test_my_model_b_fixture_csv = """
id,string_b
1,b
"""
