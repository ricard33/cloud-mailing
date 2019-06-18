/**
 * Created by ricard on 25/11/2015.
 */


(function () {
    'use strict';

    angular.module('cm.auth', ['ngCookies', 'cm.services', 'gettext', 'cm.alert'])
        .factory('auth', AuthenticationService)
        .constant('AUTH_EVENTS', {
            loginSuccess: 'auth-login-success',
            loginFailed: 'auth-login-failed',
            logoutSuccess: 'auth-logout-success',
            sessionTimeout: 'auth-session-timeout',
            notAuthenticated: 'auth-not-authenticated',
            notAuthorized: 'auth-not-authorized'
        })
        .config(configInterceptor)
        .run(loadAuthentication)
        .factory('AuthInterceptor', AuthInterceptor)
    ;

    function AuthenticationService($http, $cookies, $rootScope, $log, $q, AUTH_EVENTS, api, gettextCatalog, alert) {
        var service = {};
        var currentUser;

        service.getCurrentUser = getCurrentUser;
        service.isAdmin = isAdmin;
        service.login = login;
        service.logout = logout;
        service.setCredentials = setCredentials;
        service.clearCredentials = clearCredentials;

        return service;

        function loadCurrentUser() {
            currentUser = api.authenticate.get();
        }

        function getCurrentUser() {
            if (currentUser === undefined) {
                loadCurrentUser();
            }
            return currentUser;
        }

        function isAdmin(user) {
            // if (!user.$resolved)
            //     return false;
            return user.is_superuser ? true : false;
        }

        function login(username, password) {
            return $http.post(api.base_url + '/api/authenticate', {username: username, password: password}).then(
                function (response) {
                    $log.info("Login success for %s", username);
                    loadCurrentUser();
                    $rootScope.$broadcast(AUTH_EVENTS.loginSuccess);
                    setCredentials(username, password);
                    return response;
                },
                function (error) {
                    $log.error("Login error", error);
                    $rootScope.$broadcast(AUTH_EVENTS.loginFailed);
                    var errorMessage = error.data.detail;
                    if(errorMessage === undefined && error.status === 401){
                        errorMessage = gettextCatalog.getString("Authentication failed for {{username}}: username/password rejected by server.", {username: username});
                    }
                    alert.error(gettextCatalog.getString("Login failed: {{reason}}", {reason: errorMessage}));
                    return $q.reject(errorMessage);
                });

        }

        function logout() {
            return $http.post(api.base_url + '/api/logout')
                .then(function (response) {
                    clearCredentials();
                    $rootScope.$broadcast(AUTH_EVENTS.logoutSuccess);
                    return response;
                });

        }

        function setCredentials(username, password) {
            var authdata = Base64.encode(username + ':' + password);

            $http.defaults.headers.common['Authorization'] = 'Basic ' + authdata;
            $cookies.put('mf_authdata', authdata);
        }

        function clearCredentials() {
            $log.info("Clear credentials");
            $cookies.remove('mf_authdata');
            currentUser = undefined;
            $http.defaults.headers.common.Authorization = 'Basic';
        }
    }

    function loadAuthentication($rootScope, $state, $cookies, $http, $log, auth) {
        // keep user logged in after page refresh
        var authdata = $cookies.get('mf_authdata');
        if (authdata) {
            $http.defaults.headers.common['Authorization'] = 'Basic ' + authdata;
        }

        // eslint-disable-next-line angular/on-watch
        $rootScope.$on('$stateChangeStart', function (event, toState, toParams, fromState, fromParams) {  // eslint-disable-line no-unused-vars
            // redirect to login page if not logged in and trying to access a restricted page
            // $log.debug("entering to state", toState);
            auth.getCurrentUser().$promise.then(
                function (/*user*/) {
                    if (toState.name === 'login') {
                        event.preventDefault();
                        $state.go('index');
                    }
                },
                function (/*error*/) {
                    // not logged
                    var restrictedPage = ['login', 'about'].indexOf(toState.name) === -1;
                    if (restrictedPage) {
                        $log.debug("Not logged user requesting page '" + toState.name + "'");
                        event.preventDefault();
                        $state.go('login');
                    }
                });

        });
    }

    function configInterceptor($httpProvider) {
        $httpProvider.defaults.withCredentials = true;
        $httpProvider.interceptors.push([
            '$injector',
            function ($injector) {
                return $injector.get('AuthInterceptor');
            }
        ]);
    }

    function AuthInterceptor($rootScope, $q,
                             AUTH_EVENTS) {
        return {
            responseError: function (response) {
                // $log.warn("Authentication session ended.", response.status);
                var event = {
                    401: AUTH_EVENTS.notAuthenticated,
                    403: AUTH_EVENTS.notAuthorized,
                    419: AUTH_EVENTS.sessionTimeout,
                    440: AUTH_EVENTS.sessionTimeout
                }[response.status];
                if (event !== undefined)
                    $rootScope.$broadcast(event, response);
                return $q.reject(response);
            }
        };
    }


    // Base64 encoding service used by AuthenticationService
    var Base64 = {

        keyStr: 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=',

        encode: function (input) {
            var output = "";
            var chr1, chr2, chr3 = "";
            var enc1, enc2, enc3, enc4 = "";
            var i = 0;

            do {
                chr1 = input.charCodeAt(i++);
                chr2 = input.charCodeAt(i++);
                chr3 = input.charCodeAt(i++);

                enc1 = chr1 >> 2;
                enc2 = ((chr1 & 3) << 4) | (chr2 >> 4);
                enc3 = ((chr2 & 15) << 2) | (chr3 >> 6);
                enc4 = chr3 & 63;

                if (isNaN(chr2)) {
                    enc3 = enc4 = 64;
                } else if (isNaN(chr3)) {
                    enc4 = 64;
                }

                output = output +
                    this.keyStr.charAt(enc1) +
                    this.keyStr.charAt(enc2) +
                    this.keyStr.charAt(enc3) +
                    this.keyStr.charAt(enc4);
                chr1 = chr2 = chr3 = "";
                enc1 = enc2 = enc3 = enc4 = "";
            } while (i < input.length);

            return output;
        },

        decode: function (input) {
            var output = "";
            var chr1, chr2, chr3 = "";
            var enc1, enc2, enc3, enc4 = "";
            var i = 0;

            // remove all characters that are not A-Z, a-z, 0-9, +, /, or =
            var base64test = /[^A-Za-z0-9\+\/\=]/g;
            if (base64test.exec(input)) {
                window.alert("There were invalid base64 characters in the input text.\n" +
                    "Valid base64 characters are A-Z, a-z, 0-9, '+', '/',and '='\n" +
                    "Expect errors in decoding.");
            }
            input = input.replace(/[^A-Za-z0-9\+\/\=]/g, "");

            do {
                enc1 = this.keyStr.indexOf(input.charAt(i++));
                enc2 = this.keyStr.indexOf(input.charAt(i++));
                enc3 = this.keyStr.indexOf(input.charAt(i++));
                enc4 = this.keyStr.indexOf(input.charAt(i++));

                chr1 = (enc1 << 2) | (enc2 >> 4);
                chr2 = ((enc2 & 15) << 4) | (enc3 >> 2);
                chr3 = ((enc3 & 3) << 6) | enc4;

                output = output + String.fromCharCode(chr1);

                if (enc3 != 64) {
                    output = output + String.fromCharCode(chr2);
                }
                if (enc4 != 64) {
                    output = output + String.fromCharCode(chr3);
                }

                chr1 = chr2 = chr3 = "";
                enc1 = enc2 = enc3 = enc4 = "";

            } while (i < input.length);

            return output;
        }
    };

})();
