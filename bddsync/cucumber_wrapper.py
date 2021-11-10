import glob
import os
import re

from typing import List

STEP_KEYWORDS = ['given', 'when', 'then', 'and', 'but']


class TestPlan:

    def __init__(self, tag, test_plan_id):
        self.tag = tag
        self.id = test_plan_id


class TestSet:

    def __init__(self, tag, test_set_id):
        self.tag = tag
        self.id = test_set_id


class Scenario:

    def __init__(self, cucumber, feature, line, name, outline, tags, body):
        self.cucumber: CucumberWrapper = cucumber
        self.feature: Feature = feature
        self.line: str = line
        self.name: str = name
        self.outline: bool = outline
        self.tags: List[str] = tags
        self.body: str = body

        self.test_id = None
        self.test_plans: List[TestPlan] = []
        self.test_sets: List[TestSet] = []
        self.platform_names: List[str] = []
        self.effective_tags = tags + feature.tags

        self._find_test_id()
        self._find_test_plans()
        self._find_test_sets()

    def __str__(self):
        return f'Scenario (name="{self.name}")'

    def _find_test_id(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            for tag in self.tags:
                match = re.findall(r'^\w+-\d+$', tag)
                if match:
                    self.test_id = match[0]
                    return

    def _find_test_plans(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            test_plans = []
            for tag in self.effective_tags:
                match = re.findall(r'^tp:(.+)$', tag)
                if match:
                    test_plans.append(match[0])

            repository_test_plans = self.cucumber.config['test_plans']
            for test_plan in test_plans:
                for repository_test_plan in repository_test_plans:
                    if repository_test_plan['tag'] == test_plan:
                        self.test_plans.append(TestPlan(repository_test_plan['tag'], repository_test_plan['id']))

    def _find_test_sets(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            test_sets = []
            for tag in self.effective_tags:
                match = re.findall(r'^ts:(.+)$', tag)
                if match:
                    test_sets.append(match[0])

            repository_test_sets = self.cucumber.config['test_sets']
            for test_set in test_sets:
                for repository_test_set in repository_test_sets:
                    if repository_test_set['tag'] == test_set:
                        self.test_sets.append(TestSet(repository_test_set['tag'], repository_test_set['id']))

    @property
    def _tags_block(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            tags = set(self.tags)
            tags_line1 = ['@automated']
            tags.discard('automated')
            if self.test_id:
                tags_line1.append('@' + self.test_id)
                tags.discard(self.test_id)
            for test_plan in self.test_plans:
                if 'tp:' + test_plan.tag not in self.feature.tags:
                    tags_line1.append('@tp:' + test_plan.tag)
                tags.discard('tp:' + test_plan.tag)
            for test_set in self.test_sets:
                if 'ts:' + test_set.tag not in self.feature.tags:
                    tags_line1.append('@ts:' + test_set.tag)
                tags.discard('ts:' + test_set.tag)
            tags_line2 = ['@' + tag for tag in sorted(tags)]
            return '  ' + ' '.join(tags_line1) + '\n  ' + ' '.join(tags_line2) + '\n'

    @property
    def _name_block(self):
        return ('  Scenario Outline: ' if self.outline else '  Scenario: ') + self.name + '\n'

    @property
    def _body_block(self):
        return '\n'.join(self.body) + '\n'

    @property
    def text(self):
        return self._tags_block + self._name_block + self._body_block


class Feature:

    def __init__(self, cucumber, path, line: int, name: str, tags: list, body: list):
        self.cucumber: CucumberWrapper = cucumber
        self.path: str = path
        self.name: str = name
        self.tags: List[str] = tags
        self.line: int = line
        self.body: List[str] = body

        self.scenarios: List[Scenario] = []
        self.test_plans: List[TestPlan] = []

        self._find_test_plans()

    def __str__(self):
        return f'Feature (name="{self.name}")'

    def add_scenario(self, scenario: Scenario):
        self.scenarios.append(scenario)

    def repair_tags(self):
        text = self.text
        for scenario in self.scenarios:
            text += scenario.text

        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(text)

    def _find_test_plans(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            test_plans = []
            for tag in self.tags:
                match = re.findall(r'^tp:(.+)$', tag)
                if match:
                    test_plans.append(match[0])

            repository_test_plans = self.cucumber.config['test_plans']
            for test_plan in test_plans:
                for repository_test_plan in repository_test_plans:
                    if repository_test_plan['tag'] == test_plan:
                        self.test_plans.append(TestPlan(repository_test_plan['tag'], repository_test_plan['id']))

    @property
    def _tags_block(self):
        if self.cucumber.config['test_repository_type'] == 'xray':
            tags = set(self.tags)
            tags_line1 = []
            for test_plan in self.test_plans:
                tags_line1.append('@tp:' + test_plan.tag)
                tags.discard('tp:' + test_plan.tag)
            tags_line2 = ['@' + tag for tag in sorted(tags)]
            return ' '.join(tags_line1) + '\n' + ' '.join(tags_line2) + '\n'

    @property
    def _name_block(self):
        return 'Feature: ' + self.name + '\n'

    @property
    def _body_block(self):
        return '\n'.join(self.body) + '\n'

    @property
    def text(self):
        return self._tags_block + self._name_block + self._body_block


class CucumberWrapper:

    def __init__(self, config):
        self.config = config
        self.features_root_path: str = config['features']
        self.result: str = config['result']
        self.features_re_path: str = os.path.join(self.features_root_path, '**/*.feature')

    @property
    def features(self) -> List[Feature]:
        return self.get_features(self.features_re_path)

    def get_features(self, re_path) -> List[Feature]:
        features = []
        feature_paths = [f.replace(os.sep, '/') for f in glob.glob(re_path, recursive=True)]
        for path in feature_paths:
            features.append(self.read_feature(path))
        return features

    @staticmethod
    def _is_line_of_tags(line):
        return line.strip().startswith('@')

    def read_feature(self, path) -> Feature:
        with open(path, 'r', encoding='utf-8') as feature_file:
            lines = feature_file.readlines()

        feature_index = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('Feature'):
                feature_index = i
        scenario_indexes = []
        for i, line in enumerate(lines):
            if line.strip().startswith('Scenario'):
                scenario_indexes.append(i)

        if not scenario_indexes:
            raise Exception(f'No scenarios found in: "{path}"')

        feature_line = lines[feature_index].strip()
        feature_name = feature_line.split('Feature: ')[1]
        feature_tags = []
        for line in lines[:feature_index]:
            if self._is_line_of_tags(line):
                feature_tags += [x.lstrip('@') for x in line.split()]

        feature_body = []
        for line in lines[feature_index + 1:scenario_indexes[0]]:
            if self._is_line_of_tags(line):
                break
            feature_body.append(line.rstrip())

        feature = Feature(self, path, feature_index + 1, feature_name, feature_tags, feature_body)

        for i, index in enumerate(scenario_indexes):
            scenario_line = lines[index].strip()
            outline = scenario_line.startswith('Scenario Outline: ')
            try:
                name = scenario_line.split('Scenario Outline: ' if outline else 'Scenario: ')[1]
            except IndexError:
                raise Exception(f'No scenario name found at line {index + 1}')

            tags = []
            tag_row = 1
            tag_line = lines[index - tag_row]
            while self._is_line_of_tags(tag_line):
                tags = [x.lstrip('@') for x in lines[index - tag_row].split()] + tags
                tag_row += 1
                tag_line = lines[index - tag_row]

            body = []
            next_index = len(lines) if index == scenario_indexes[-1] else scenario_indexes[i + 1]
            for line in lines[index + 1:next_index]:
                if self._is_line_of_tags(line):
                    break
                body.append(line.rstrip())

            feature.add_scenario(Scenario(self, feature, index + 1, name, outline, tags, body))

        return feature


