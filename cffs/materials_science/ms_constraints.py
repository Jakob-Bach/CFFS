"""MS constraints

Classes to evaluate specific constraints for materials science use cases.
"""

from abc import ABCMeta, abstractmethod
import random
import re
from typing import Any, Dict, Iterable, Type

import pandas as pd

from cffs.core import combi_expressions as expr
from cffs.core import combi_solving as solv
from cffs.materials_science import ms_data_utility


SCHMID_GROUPS_100 = [[1, 2, 5, 6, 7, 8, 11, 12], [3, 4, 9, 10]]  # for (1 0 0) orientation


class MSConstraintEvaluator(metaclass=ABCMeta):

    def __init__(self, problem: solv.Problem):
        self.problem = problem

    @abstractmethod
    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        raise NotImplementedError('Abstract method.')

    def evaluate_constraints(self) -> Dict[str, float]:
        random.seed(25)
        for constraint in self.get_constraints():
            self.problem.add_constraint(constraint)
        frac_solutions = self.problem.estimate_solution_fraction(iterations=10000)
        result = self.problem.optimize()
        result['num_constraints'] = self.problem.get_num_constraints()
        result['frac_solutions'] = frac_solutions
        self.problem.clear_constraints()
        return result


# Combines constraints from contained evaluators
class ContainerEvaluator(MSConstraintEvaluator, metaclass=ABCMeta):

    @abstractmethod
    def get_member_evaluators(self) -> Iterable[MSConstraintEvaluator]:
        raise NotImplementedError('Abstract method.')

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        for evaluator in self.get_member_evaluators():
            constraints.extend(evaluator.get_constraints())
        return constraints


# Implementation of CombinedEvaluator which stores member evaluators in an attribute
class CombinedEvaluator(ContainerEvaluator):

    # for member evaluators, pass type and initialization arguments
    def __init__(self, problem: solv.Problem, evaluators: Dict[Type[MSConstraintEvaluator], Dict[str, Any]] = None):
        super().__init__(problem=problem)
        self.evaluators = [type_object(**{'problem': problem, **args_dict})
                           for type_object, args_dict in evaluators.items()]

    def get_member_evaluators(self) -> Iterable[MSConstraintEvaluator]:
        return self.evaluators


class NoConstraintEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        return []


# From set of all features, select at most a certain amount (global cardinality constraint)
class GlobalAtMostEvaluator(MSConstraintEvaluator):

    def __init__(self, problem: solv.Problem, global_at_most: int = 10):
        super().__init__(problem=problem)
        self.global_at_most = global_at_most

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        return [expr.AtMost(self.problem.get_variables(), self.global_at_most)]


# Select only features with at least a certain quality
class QualityThresholdEvaluator(MSConstraintEvaluator):

    def __init__(self, problem: solv.Problem, threshold: float):
        super().__init__(problem=problem)
        self.threshold = threshold

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        return [expr.Not(v) for v, q in zip(self.problem.get_variables(), self.problem.get_qualities())
                if q < self.threshold]


# Do not select two features at same time which are correlated over a certain amount
class CorrelationRemovalEvaluator(MSConstraintEvaluator):

    def __init__(self, problem: solv.Problem, corr_df: pd.DataFrame, threshold: float):
        assert corr_df.shape[0] == len(problem.get_variables())
        assert corr_df.shape[1] == len(problem.get_variables())
        super().__init__(problem=problem)
        self.correlation_pairs = [(i, j) for i in range(len(corr_df)) for j in range(i)
                                  if corr_df.iat[i, j] >= threshold]

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        return [expr.Not(expr.And([self.problem.get_variables()[i], self.problem.get_variables()[j]]))
                for i, j in self.correlation_pairs]


# For Schmid factor (1 0 0) grouping, select features from at most one group
class SelectSchmidGroupEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        variable_groups = []
        for slip_group in SCHMID_GROUPS_100:
            variable_group = [variable for variable in self.problem.get_variables()
                              if re.search('_(' + '|'.join([str(i) for i in slip_group]) + ')$',
                                           variable.get_name()) is not None]
            variable_groups.append(variable_group)
        return [expr.AtMost([expr.Or(x) for x in variable_groups], 1)]


# For each quantity, for Schmid factor (1 0 0) grouping, select features from at most one group
class SelectQuantitySchmidGroupEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        base_quantities = [variable.get_name().replace('_1', '') for variable in self.problem.get_variables()
                           if variable.get_name().endswith('_1')]
        for quantity in base_quantities:
            variable_groups = []
            for slip_group in SCHMID_GROUPS_100:
                variable_group = [variable for variable in self.problem.get_variables()
                                  if re.search(quantity + '_(' + '|'.join([str(i) for i in slip_group]) + ')$',
                                               variable.get_name()) is not None]
                variable_groups.append(variable_group)
            constraints.append(expr.AtMost([expr.Or(x) for x in variable_groups], 1))
        return constraints


# For Schmid factor (1 0 0) grouping, select at most one feature from each group
class SelectSchmidGroupRepresentativeEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        for slip_group in SCHMID_GROUPS_100:
            variable_group = [variable for variable in self.problem.get_variables()
                              if re.search('_(' + '|'.join([str(i) for i in slip_group]) + ')$',
                                           variable.get_name()) is not None]
            if len(variable_group) > 0:  # z3.AtMost not defined if applied to empty list
                constraints.append(expr.AtMost(variable_group, 1))
        return constraints


# For each quantity, for Schmid factor (1 0 0) grouping, select at most one feature from each group
class SelectQuantitySchmidGroupRepresentativeEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        base_quantities = [variable.get_name().replace('_1', '') for variable in self.problem.get_variables()
                           if variable.get_name().endswith('_1')]
        for quantity in base_quantities:
            for slip_group in SCHMID_GROUPS_100:
                variable_group = [variable for variable in self.problem.get_variables()
                                  if re.search(quantity + '_(' + '|'.join([str(i) for i in slip_group]) + ')$',
                                               variable.get_name()) is not None]
                if len(variable_group) > 0:  # z3.AtMost not defined if applied to empty list
                    constraints.append(expr.AtMost(variable_group, 1))
        return constraints


# For each slip system, select either all quantities from that slip system or none
class SelectWholeSlipSystemsEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        for slip_system in range(1, 13):
            variable_group = [variable for variable in self.problem.get_variables()
                              if variable.get_name().endswith('_' + str(slip_system))]
            constraints.append(expr.Iff(variable_group))
        return constraints


# From reaction features, select features belonging to at most one reaction type
class SelectReactionTypeEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        variable_groups = []
        for reaction_type in ms_data_utility.REACTION_TYPES:
            variable_group = [variable for variable in self.problem.get_variables()
                              if reaction_type in variable.get_name()]
            variable_groups.append(variable_group)
        return [expr.AtMost([expr.Or(x) for x in variable_groups], 1)]


# For each quantity, select either absolute value or delta value or none
class SelectValueOrDeltaEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        delta_variables = [variable for variable in self.problem.get_variables()
                           if 'delta_' in variable.get_name()]
        for delta_variable in delta_variables:
            variable_name = delta_variable.get_name().replace('delta_', '')
            for variable in self.problem.get_variables():
                if variable.get_name() == variable_name:
                    constraints.append(expr.Not(expr.And([variable, delta_variable])))
                    break
        return constraints


# From plastic strain tensor, select at most three directions
class SelectStrainTensorEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        variable_groups = []
        directions = [variable.get_name().replace('eps_', '') for variable in self.problem.get_variables()
                      if re.match('eps_[a-z]{2}$', variable.get_name())]
        if len(directions) == 0:
            return []  # z3.AtMost not defined if applied to empty list
        for direction in directions:
            variable_group = [variable for variable in self.problem.get_variables()
                              if 'eps_' + direction in variable.get_name()]
            variable_groups.append(variable_group)
        return [expr.AtMost([expr.Or(x) for x in variable_groups], 3)]


# For dislocation density, select at most one from three feature groups which all describe it
class SelectDislocationDensityEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        variable_groups = []
        quantity_patterns = ['rho_(' + '|'.join(ms_data_utility.AGGREGATES) + ')',
                             'mean_free_path', 'free_path_per_voxel']
        if len(quantity_patterns) == 0:
            return []  # z3.AtMost not defined if applied to empty list
        for pattern in quantity_patterns:
            variable_group = [variable for variable in self.problem.get_variables()
                              if re.search(pattern, variable.get_name()) is not None]
            variable_groups.append(variable_group)
        return [expr.AtMost([expr.Or(x) for x in variable_groups], 1)]


# For strain rate computation, select at most one type
class SelectStrainRateEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        gamma_variables = [variable for variable in self.problem.get_variables()
                           if 'gamma' in variable.get_name()]
        gamma_abs_variables = [variable for variable in gamma_variables
                               if 'gamma_abs' in variable.get_name()]
        gamma_variables = [variable for variable in gamma_variables
                           if 'gamma_abs' not in variable.get_name()]
        return [expr.Not(expr.And([expr.Or(gamma_variables), expr.Or(gamma_abs_variables)]))]


# Over all quantities, select at most one type of aggregate
class SelectAggregateEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        variable_groups = []
        for aggregate in ms_data_utility.AGGREGATES:
            variable_group = [variable for variable in self.problem.get_variables()
                              if variable.get_name().endswith('_' + aggregate)]
            variable_groups.append(variable_group)
        return [expr.AtMost([expr.Or(x) for x in variable_groups], 1)]


# For each quantity, select at most one type of aggregate
class SelectQuantityAggregateEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        base_quantities = [variable.get_name().replace('_1', '') for variable in self.problem.get_variables()
                           if variable.get_name().endswith('_1')]
        for quantity in base_quantities:
            aggregate_variables = [variable for variable in self.problem.get_variables()
                                   if re.search(quantity + '_(' + '|'.join(ms_data_utility.AGGREGATES) + ')$',
                                                variable.get_name()) is not None]
            if len(aggregate_variables) > 0:  # z3.AtMost not defined if applied to empty list
                constraints.append(expr.AtMost(aggregate_variables, 1))
        return constraints


# For each quantity, select either aggregates or orignal values or none
class SelectAggregateOrOriginalEvaluator(MSConstraintEvaluator):

    def get_constraints(self) -> Iterable[expr.BooleanExpression]:
        constraints = []
        base_quantities = [variable.get_name().replace('_1', '') for variable in self.problem.get_variables()
                           if variable.get_name().endswith('_1')]
        for quantity in base_quantities:
            original_variables = [variable for variable in self.problem.get_variables()
                                  if re.search(quantity + '_[0-9]+$', variable.get_name()) is not None]
            aggregate_variables = [variable for variable in self.problem.get_variables()
                                   if re.search(quantity + '_(' + '|'.join(ms_data_utility.AGGREGATES) + ')$',
                                                variable.get_name()) is not None]
            constraints.append(expr.Not(expr.And([expr.Or(original_variables), expr.Or(aggregate_variables)])))
        return constraints
