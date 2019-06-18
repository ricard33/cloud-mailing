(function () {
    'use strict';
    angular.module('cm.login')
        .directive('loginDialog', loginDialog)
    ;

    function loginDialog(AUTH_EVENTS) {
        return {
            restrict: 'A',
            controller: 'LoginController as login_vm',
            template: '<div ng-if="visible" ng-include = "\'login/login.html\'" > ',
            link: function (scope) {
                var showDialog = function () {
                    scope.visible = true;
                };

                scope.visible = false;
                scope.$on(AUTH_EVENTS.notAuthenticated, showDialog);
                scope.$on(AUTH_EVENTS.sessionTimeout, showDialog)
            }
        };
    }
})();
