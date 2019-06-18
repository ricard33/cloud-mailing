(function () {
    'use strict';
    angular.module('cm.login')
        .controller('LoginController', LoginController);

    function LoginController(auth, $state, $log, $rootScope, AUTH_EVENTS) {
        var vm = this;
        vm.username = undefined;
        vm.password = undefined;
        vm.login = login;

        function login() {
            vm.dataLoading = true;
            return auth.login(vm.username, vm.password).then(
                function (data) {
                    $state.go("index");
                },
                function (error) {
                    $log.error("Login error");
                    vm.dataLoading = false;
                });
        }
    }
})();
